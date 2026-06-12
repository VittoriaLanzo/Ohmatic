"""vLLM-backed generation backend for Ohmatic.

CONTINUOUS BATCHING is the point: all prompts go in one LLM.generate() call, filling
the GPU with concurrent sequences instead of the HF one-at-a-time loop (8-12x on the
STaR harvest, 5-8x on prod_eval).

vllm is NOT installed locally; the import is fully lazy so py_compile/CI pass without it.

API: generate(batch, ...) -> list[list[str]]; __call__(messages, ...) -> list[str]
(drop-in for _Gen.__call__); chat(messages) -> str (drop-in for HFChatModel.chat).
"""
from __future__ import annotations

import sys
from typing import Any


class VLLMChatModel:
    """vLLM-backed chat model serving a FULLY-MERGED model on disk.

    model_dir must be a complete plain HF model (no LoRA layers), merged via
    train/merge_adapter.py upstream: vLLM does NOT support PEFT LoRA at serve time
    here, so merge-first is required (same as the prod eval path).

    max_model_len must cover system prompt + user prompt + max_new_tokens.
    dtype='bfloat16' matches HF training (avoids fp16 overflow on long circuits).
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

        # Keep a HF tokenizer for apply_chat_template (vLLM does not expose it stably).
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
        """Apply chat template - identical to HFChatModel.chat and _Gen.__call__."""
        # enable_thinking=False matches pipeline.py + _Gen; TypeError guard covers
        # tokenizers that don't know enable_thinking.
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
        """Batched generation over conversations: ONE LLM.generate() over all prompts
        so vLLM's continuous-batching scheduler saturates the GPU.

        greedy=True forces temperature=0 (matches HFChatModel.chat's do_sample=False).
        Returns list[list[str]] (outer=prompt, inner=sample of length n), input order.
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

        # Over-length pre-filter: skip any prompt with no room left for generation
        # (budget = max_model_len - max_tok) so one long prompt can NEVER crash the batch.
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

        # ONE vLLM call over all valid prompts (continuous batching), one RequestOutput
        # per prompt in input order. Catch ValueError so one bad prompt cannot crash the batch.
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
        """Single-prompt drop-in matching _Gen.__call__ (returns list[str]).

        Kept for compatibility/fallback; the vllm harvest path uses batched generate()
        directly. The over-length pre-filter applies: an oversize prompt returns [],
        which the harvest loop treats as no candidates and skips gracefully.
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
        """Single-prompt greedy single completion - drop-in for HFChatModel.chat
        (used by OhmaticPipeline when backend='vllm')."""
        completions = self(messages, do_sample=False, n=1)
        return completions[0] if completions else ""
