"""
inference/vllm_backend.py
=========================
vLLM-backed generation backend for Ohmatic.

DESIGN
------
Replaces _Gen (train/online_correction.py) and HFChatModel (inference/pipeline.py)
with a vLLM LLM engine that performs CONTINUOUS BATCHING - all prompts are submitted
in a single vllm.LLM.generate() call, which fills GPU memory with concurrent
sequences and saturates CUDA compute.  The HF loop submits prompts one-at-a-time
(or at best num_return_sequences × one prompt at a time), leaving the GPU idle
between sequences.  Expected throughput gain: 8-12x for the STaR harvest; 5-8x for
prod_eval (depending on circuit length distribution and A40 VRAM headroom).

IMPORT SAFETY
-------------
vllm is NOT installed locally (no GPU).  The import is fully lazy - the top-level
module import never touches vllm.  py_compile passes without vllm present.

USAGE
-----
# Production (pod):
from inference.vllm_backend import VLLMChatModel

model = VLLMChatModel(
    model_dir="/workspace/merged-corr",    # fully-merged Qwen3-8B + best-erc + correction
    max_model_len=16384,
)

# Batched (harvest hot path):
results = model.generate(
    list_of_message_lists,          # list[list[dict]]
    temperature=0.7,
    top_p=0.95,
    n=4,
    max_tokens=2560,
)
# -> list[list[str]], one inner list per input prompt, length n

# Single-prompt drop-in for _Gen.__call__:
completions = model(messages, do_sample=True, temperature=0.7, top_p=0.95, n=4)
# -> list[str], length n

# Single-prompt drop-in for HFChatModel.chat:
text = model.chat(messages)
# -> str (first completion, greedy)
"""
from __future__ import annotations

import sys
from typing import Any


class VLLMChatModel:
    """vLLM-backed chat model for Ohmatic.  Serves a FULLY-MERGED model on disk.

    The model_dir must contain a complete, plain HF model (no LoRA layers):
        Qwen/Qwen3-8B + best-erc adapter + correction adapter
    merged via train/merge_adapter.py (called upstream before this class is
    instantiated).  vLLM does NOT support PEFT LoRA at serve time in this
    integration; the merge-first approach avoids that constraint and is the
    same technique used by the prod eval path.

    Args:
        model_dir       : Local path to the fully-merged HF model directory.
        max_model_len   : Maximum total context (prompt + generation) tokens.
                          Must cover the Ohmatic system prompt (~6 200 tok) +
                          the longest user prompt (~2 200 tok) + max_new_tokens (2 560).
                          Default: 16 384 (fits on A40 48 GB with gpu_mem_util=0.90;
                          Qwen3-8B supports up to 32 768).
        gpu_mem_util    : Fraction of GPU VRAM to allocate for the KV cache.
                          0.90 is the sweet spot for A40 48 GB: leaves ~4.8 GB for
                          activations while giving the scheduler maximum KV cache.
        dtype           : Weight dtype.  'bfloat16' matches HF training and avoids
                          the fp16 overflow risk on long circuits.
        tensor_parallel : Number of GPUs.  1 for single-A40 pod.
        trust_remote_code: Required by Qwen3 (custom modelling code).
        enforce_eager   : Disable CUDA graph capture.  False (default) is faster
                          for large batches; set True only for debugging.
    """

    def __init__(
        self,
        model_dir: str,
        max_model_len: int = 16384,
        gpu_mem_util: float = 0.90,
        dtype: str = "bfloat16",
        tensor_parallel: int = 1,
        trust_remote_code: bool = True,
        enforce_eager: bool = False,
    ) -> None:
        # ── Lazy vllm import - safe on CPU-only machines (py_compile, CI) ────────
        try:
            from vllm import LLM  # type: ignore[import]
            from transformers import AutoTokenizer  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "vllm and transformers must be installed on the pod. "
                "Run: pip install 'vllm==0.6.6' transformers. "
                f"Original error: {exc}"
            ) from exc

        self._model_dir = model_dir
        self._max_tokens_default = 2560  # matches pipeline.py / _Gen default
        self._max_model_len = max_model_len

        # Load tokenizer separately - we need apply_chat_template for prompt building.
        # vLLM has its own tokenizer internally but does not expose apply_chat_template
        # in a stable public API, so we keep a HF tokenizer for that step only.
        self._tok = AutoTokenizer.from_pretrained(
            model_dir, trust_remote_code=trust_remote_code
        )

        print(
            f"[VLLMChatModel] loading {model_dir}  "
            f"max_model_len={max_model_len}  gpu_mem_util={gpu_mem_util}  "
            f"dtype={dtype}  tp={tensor_parallel}",
            file=sys.stderr,
            flush=True,
        )

        self._llm = LLM(
            model=model_dir,
            max_model_len=max_model_len,
            gpu_memory_utilization=gpu_mem_util,
            dtype=dtype,
            tensor_parallel_size=tensor_parallel,
            trust_remote_code=trust_remote_code,
            enforce_eager=enforce_eager,
        )

        print("[VLLMChatModel] engine ready.", file=sys.stderr, flush=True)

    # ── Internal prompt formatter ─────────────────────────────────────────────

    def _format_prompt(self, messages: list[dict[str, str]]) -> str:
        """Apply chat template - identical logic to HFChatModel.chat and _Gen.__call__."""
        # enable_thinking=False matches pipeline.py + _Gen exactly.
        # TypeError guard covers tokenizers that don't know enable_thinking.
        try:
            return self._tok.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            return self._tok.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )

    def _count_prompt_tokens(self, prompt_text: str) -> int:
        """Return the token count of an already-formatted prompt string."""
        return len(self._tok.encode(prompt_text))

    # ── Public batched generate ───────────────────────────────────────────────

    def generate(
        self,
        list_of_message_lists: list[list[dict[str, str]]],
        temperature: float = 0.7,
        top_p: float = 0.95,
        n: int = 1,
        max_tokens: int | None = None,
        greedy: bool = False,
    ) -> list[list[str]]:
        """Batched generation over a list of conversations.

        THE BATCHING IS THE WHOLE POINT: all prompts are submitted to vLLM in a
        single LLM.generate() call.  vLLM's continuous-batching scheduler fills
        the GPU with concurrent sequences from different prompts, saturating CUDA
        compute and avoiding the HF per-sequence overhead.

        Args:
            list_of_message_lists : Batch of conversations.  Each element is a
                                    list[dict] like [{"role":"system","content":...},
                                    {"role":"user","content":...}].
            temperature           : Sampling temperature.  Ignored when greedy=True.
            top_p                 : Nucleus sampling p.  Ignored when greedy=True.
            n                     : Number of completions per prompt.
            max_tokens            : Max new tokens per completion.  Defaults to
                                    self._max_tokens_default (2560).
            greedy                : When True, use temperature=0 (argmax decoding),
                                    matching HFChatModel.chat's do_sample=False.

        Returns:
            list[list[str]] - outer index = prompt index, inner index = sample index
            (length n).  Ordered to match the input order.
        """
        from vllm import SamplingParams  # type: ignore[import]

        if not list_of_message_lists:
            return []

        max_tok = max_tokens if max_tokens is not None else self._max_tokens_default

        # Build sampling params - greedy: temperature=0, top_p/top_k irrelevant.
        if greedy:
            sampling_params = SamplingParams(
                n=n,
                temperature=0,
                max_tokens=max_tok,
            )
        else:
            sampling_params = SamplingParams(
                n=n,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tok,
            )

        # Build flat list of formatted prompt strings.
        raw_prompts: list[str] = [
            self._format_prompt(msgs) for msgs in list_of_message_lists
        ]

        # ── Over-length pre-filter ────────────────────────────────────────────
        # Any prompt whose token count leaves no room for generation is skipped
        # here so a single long prompt can NEVER crash the entire batch.
        # Budget: max_model_len - max_tok tokens reserved for generation output.
        input_budget = self._max_model_len - max_tok
        valid_indices: list[int] = []
        skipped_count = 0
        for idx, p in enumerate(raw_prompts):
            tok_count = self._count_prompt_tokens(p)
            if tok_count > input_budget:
                print(
                    f"[VLLMChatModel.generate] SKIP prompt[{idx}]: "
                    f"{tok_count} input tokens > budget {input_budget} "
                    f"(max_model_len={self._max_model_len}, max_tok={max_tok})",
                    file=sys.stderr,
                    flush=True,
                )
                skipped_count += 1
            else:
                valid_indices.append(idx)

        if skipped_count:
            print(
                f"[VLLMChatModel.generate] skipped {skipped_count} over-length "
                f"prompt(s) out of {len(raw_prompts)}",
                file=sys.stderr,
                flush=True,
            )

        # Build result list pre-filled with empty completions for skipped prompts.
        results: list[list[str]] = [[] for _ in raw_prompts]

        if not valid_indices:
            return results

        prompts: list[str] = [raw_prompts[i] for i in valid_indices]

        # ONE vLLM call over ALL valid prompts - continuous batching happens here.
        # vLLM returns one RequestOutput per prompt, preserving input order.
        # Belt-and-suspenders: catch per-request ValueError so one bad prompt
        # cannot crash the whole batch even after the pre-filter.
        try:
            outputs = self._llm.generate(prompts, sampling_params)
        except ValueError as exc:
            # Should not happen after pre-filter, but guard anyway.
            print(
                f"[VLLMChatModel.generate] vLLM ValueError on batch: {exc} - "
                "returning empty completions for all prompts in this batch.",
                file=sys.stderr,
                flush=True,
            )
            return results

        # Decode: map outputs back to original indices.
        for out_idx, req_output in enumerate(outputs):
            orig_idx = valid_indices[out_idx]
            completions = [co.text.strip() for co in req_output.outputs]
            results[orig_idx] = completions

        return results

    # ── Drop-in for _Gen.__call__ (harvest loop) ──────────────────────────────

    def __call__(
        self,
        messages: list[dict[str, str]],
        do_sample: bool = True,
        temperature: float = 0.7,
        top_p: float = 0.95,
        n: int = 1,
    ) -> list[str]:
        """Single-prompt wrapper matching _Gen.__call__'s signature exactly.

        harvest() calls gen(messages, do_sample=..., temperature=..., top_p=..., n=...)
        and expects list[str].  This wrapper makes VLLMChatModel a drop-in.

        NOTE: In normal harvest use (--backend vllm) the harvest loop is replaced
        by a batched variant that calls generate() directly on a whole-prompt batch.
        This method is kept for compatibility / fallback / testing only.

        The over-length pre-filter inside generate() applies here too: if the
        single prompt exceeds the input budget, generate() returns [[]] and this
        method returns [] - the harvest correction loop interprets an empty list
        as no valid candidates and skips the prompt gracefully.
        """
        results = self.generate(
            [messages],
            temperature=temperature,
            top_p=top_p,
            n=n,
            greedy=not do_sample,
        )
        return results[0] if results else []

    # ── Drop-in for HFChatModel.chat (pipeline) ───────────────────────────────

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Single-prompt, greedy, single completion - matches HFChatModel.chat.

        Used by OhmaticPipeline when backend='vllm'.
        """
        completions = self(messages, do_sample=False, n=1)
        return completions[0] if completions else ""
