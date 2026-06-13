"""Cross-model benchmark client implementations.

Every adapter exposes run(system_prompt, user_prompt) -> dict returning a uniform
row fragment (raw_output, latency_s, tokens_in/out; Ohmatic legs also ok, blocked,
attempts, delivered_circuit_json, user_message, normalized_prompt).

IP boundary: hosted legs are SINGLE-SHOT (pass@1) on the byte-identical system
prompt + user turn; the ERC feedback loop is proprietary, never offered to hosted
competitors (disclosed in the report). Ohmatic legs run the full product pipeline:
T5 (realuser only) -> Qwen -> ERC -> up to 3 corrections -> killswitch.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval.benchmark.cross_model import config as C


# ── Hosted: Anthropic ─────────────────────────────────────────────────────────

class AnthropicAdapter:
    def __init__(self, model: str):
        import anthropic
        self.client = anthropic.Anthropic()          # ANTHROPIC_API_KEY from env
        self.model = model

    def run(self, system_prompt: str, user_prompt: str) -> dict:
        t0 = time.time()
        # cache_control on the constant system prompt: identical bytes across the
        # suite, so input cost mostly evaporates after request 1. Adaptive models
        # reject sampling params, so none sent.
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=C.MAX_TOKENS,
            system=[{"type": "text", "text": system_prompt,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        u = resp.usage
        return {
            "raw_output": text,
            "latency_s": round(time.time() - t0, 3),
            "tokens_in": (u.input_tokens or 0)
                         + getattr(u, "cache_creation_input_tokens", 0)
                         + getattr(u, "cache_read_input_tokens", 0),
            "tokens_out": u.output_tokens or 0,
        }


# ── Hosted/local: OpenAI-compatible ──────────────────────────────────────────

class OpenAICompatAdapter:
    """Covers Codex (api.openai.com) AND any OpenAI-compatible endpoint via
    OPENAI_BASE_URL - that's the plug-and-play reproducibility hook."""

    def __init__(self, model: str):
        from openai import OpenAI
        kw = {}
        if os.environ.get("OPENAI_BASE_URL"):
            kw["base_url"] = os.environ["OPENAI_BASE_URL"]
        self.client = OpenAI(**kw)                   # OPENAI_API_KEY from env
        self.model = (os.environ.get("OPENAI_MODEL", "")
                      if model == "env:OPENAI_MODEL" else model)
        if not self.model:
            raise SystemExit("Set OPENAI_MODEL (e.g. the Codex model id).")

    def run(self, system_prompt: str, user_prompt: str) -> dict:
        t0 = time.time()
        kw = dict(model=self.model,
                  messages=[{"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}],
                  max_completion_tokens=C.MAX_TOKENS)
        try:                                          # temp-pinned where allowed
            resp = self.client.chat.completions.create(temperature=C.TEMPERATURE, **kw)
        except Exception:
            resp = self.client.chat.completions.create(**kw)
        u = resp.usage
        return {
            "raw_output": resp.choices[0].message.content or "",
            "latency_s": round(time.time() - t0, 3),
            "tokens_in": getattr(u, "prompt_tokens", 0) or 0,
            "tokens_out": getattr(u, "completion_tokens", 0) or 0,
        }


# ── Local: the full Ohmatic product pipeline ──────────────────────────────────

class OhmaticAdapter:
    """End-to-end product (T5 -> Qwen -> ERC -> retries -> killswitch). Wraps
    OhmaticPipeline: same code prod serves, zero benchmark-special behavior."""

    def __init__(self, cfg: dict, use_t5: bool):
        from inference.pipeline import (OhmaticPipeline, PipelineConfig,
                                        _MockNormalizer, HFT5Normalizer,
                                        _build_system_prompt)
        normalizer = (_MockNormalizer() if (not use_t5 or cfg.get("no_t5"))
                      else HFT5Normalizer(C.T5_NORMALIZER))

        backend = cfg.get("backend", "hf")
        if backend == "llamacpp":
            # Use the PRODUCT's LlamaCppChatModel so this leg is byte-identical to
            # what ships: enable_thinking=False via the model tokenizer. The plain
            # chat template defaults thinking ON, which underperformed (73.5% vs the
            # bf16 leg's 93.3%) - that was a benchmark misconfiguration, now fixed.
            from huggingface_hub import hf_hub_download, snapshot_download
            from inference.pipeline import LlamaCppChatModel
            token = os.environ.get("HF_TOKEN")
            gguf = hf_hub_download(cfg["gguf_repo"], cfg["gguf_file"], token=token)
            tok_dir = snapshot_download(
                cfg["gguf_repo"], token=token,
                allow_patterns=["tokenizer.json", "tokenizer_config.json", "vocab.json",
                                "merges.txt", "special_tokens_map.json", "added_tokens.json",
                                "chat_template.jinja", "generation_config.json"])
            generator = LlamaCppChatModel(gguf, tokenizer_dir=tok_dir,
                                          max_new_tokens=C.MAX_TOKENS)
        else:  # hf - fully-merged repo loads like any causal LM (no adapter)
            from inference.pipeline import HFChatModel
            generator = HFChatModel(cfg["qwen_model"],
                                    max_new_tokens=C.MAX_TOKENS)

        # retry_temperature pinned to C.TEMPERATURE (0.0): the benchmark must stay
        # deterministic/reproducible. The PRODUCT default samples on corrections to escape
        # greedy regeneration, but here we hold every attempt greedy so the numbers are a
        # fixed, reproducible reference (the prod retry-sampling gain is measured separately).
        self.pipeline = OhmaticPipeline(
            normalizer, generator, _build_system_prompt(),
            max_retries=C.PIPELINE_MAX_RETRIES,
            retry_temperature=C.TEMPERATURE)

    def chat_messages(self, messages: list[dict]) -> dict:
        """Correction suite: single-shot repair on the VERBATIM trained conversation.
        No T5, no retry loop (mirrors in-training correction_eval); output verified
        like any raw generation in stage 2."""
        t0 = time.time()
        text = self.pipeline.generator.chat(messages, temperature=C.TEMPERATURE)  # greedy, deterministic
        return {"raw_output": text,
                "latency_s": round(time.time() - t0, 3),
                "tokens_in": 0, "tokens_out": 0}

    def run(self, system_prompt: str, user_prompt: str) -> dict:
        # system_prompt arg ignored on purpose: the pipeline builds its own from
        # the SAME shared single source - byte-identical to what hosted legs get.
        t0 = time.time()
        r = self.pipeline.run(user_prompt)
        return {
            "raw_output": "",                       # pipeline output is structured
            "latency_s": round(time.time() - t0, 3),
            "tokens_in": 0, "tokens_out": 0,        # local: cost is pod-hours
            "ok": r.ok,
            "blocked": r.blocked,
            "attempts": r.attempts,
            "delivered_circuit_json": r.circuit_json if r.ok else "",
            "internal_final_circuit_json": r.circuit_json if not r.ok else "",
            "user_message": r.user_message,
            "normalized_prompt": r.normalized_prompt,
        }


def build_adapter(model_name: str, suite: str):
    cfg = C.model_cfg(model_name)
    kind = cfg["adapter"]
    if kind == "anthropic":
        return AnthropicAdapter(cfg["model"])
    if kind == "openai":
        return OpenAICompatAdapter(cfg["model"])
    if kind == "ohmatic":
        # T5 only for realuser (raw messy input). Holdout prompts are already
        # normalized - pass-through there, same as prod_eval.
        return OhmaticAdapter(cfg, use_t5=(suite == "realuser"))
    raise SystemExit(f"Unknown adapter kind: {kind}")
