"""Cross-model benchmark client implementations.

Every adapter exposes run(system_prompt, user_prompt) -> dict returning a uniform
row fragment (raw_output, latency_s, tokens_in/out; Ohmatic legs also ok, blocked,
attempts, delivered_circuit_json, user_message, normalized_prompt).

IP boundary: the Claude legs are SINGLE-SHOT (pass@1) on the byte-identical system
prompt + user turn, driven through the `claude -p` CLI (product vs product, NO api
key); the ERC feedback loop is proprietary, never offered to an off-box model
(disclosed in the report). Ohmatic legs run the full product pipeline:
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


# ── Claude products: subagent-driven via the `claude -p` CLI ──────────────────

class ClaudeCliAdapter:
    """Product-vs-product leg. Each ask spins up a FRESH, zero-context Claude Code
    instance through the `claude -p` CLI - the shipped product, on its own system
    prompt - with the Ohmatic format spec appended on top. The spec is what lets a
    chat model emit the circuit schema at all, so it levels the field while still
    measuring product vs product, not a bare model behind an api key.

    What keeps the leg honest and reproducible:
      * no api key  - the CLI uses the local Claude Code subscription auth;
      * zero context- a fresh temp cwd SEALED as its own git repo (see _seal_cwd) so no
                      real project's CLAUDE.md / memory / git status above it is loaded,
                      plus --setting-sources "" to drop operator hooks/skills/plugins;
      * single-shot - --allowed-tools none, so it answers in one turn, no tool use and
                      no ERC feedback loop (that loop is the proprietary Ohmatic edge);
      * verbatim    - the assistant text is stored raw and verified in stage 2 through
                      the SAME extractor + ERC path as every other leg.

    The spec is passed via --append-system-prompt-FILE (it is far larger than a
    command line allows), and the CLI's own reported total_cost_usd rides back as
    cli_cost_usd, recorded as-is (no static price table to drift)."""

    def __init__(self, model: str):
        import shutil
        self.model = model
        self.exe = shutil.which("claude")
        if not self.exe:
            raise SystemExit(
                "`claude` CLI not on PATH - the Claude legs need it "
                "(npm i -g @anthropic-ai/claude-code) plus a logged-in session.")

    @staticmethod
    def _seal_cwd(cwd: str) -> None:
        """Make `cwd` its OWN git repo so Claude Code stops walking UP at this folder
        and never reaches a real project's .git / CLAUDE.md / auto-memory above it.

        This is the cross-machine guarantee: a plain temp dir is enough on a normal box
        (the system temp is outside any repo), but on a box whose temp lives *inside* a
        git repo - e.g. a home dir that is itself a repo - the subagent would otherwise
        inherit that repo's memory + CLAUDE.md + git status. Sealing the temp dir makes
        the context identically empty everywhere. Identity + default branch are pinned to
        fixed neutral values so the leg sees the SAME empty repo on every machine, never
        the operator's global git name. Best-effort: if `git` is missing the temp dir is
        already a safe boundary on a normal box, so we proceed regardless."""
        import subprocess
        run = lambda *a: subprocess.run(a, cwd=cwd, stdin=subprocess.DEVNULL,
                                        capture_output=True, timeout=30)
        try:
            run("git", "-c", "init.defaultBranch=main", "init", "-q")
            run("git", "config", "user.name", "ohmatic-bench")
            run("git", "config", "user.email", "bench@ohmatic.local")
        except Exception:
            pass

    def run(self, system_prompt: str, user_prompt: str) -> dict:
        import json
        import subprocess
        import tempfile
        t0 = time.time()
        # Fresh, SEALED temp cwd per ask (so no ask can leave memory for the next): the
        # base Claude product prompt stays, the Ohmatic spec rides on top via
        # --append-system-prompt-file (it is far larger than a command line allows).
        with tempfile.TemporaryDirectory() as cwd:
            self._seal_cwd(cwd)
            specf = Path(cwd) / "ohmatic_spec.txt"
            specf.write_text(system_prompt, encoding="utf-8")
            argv = [self.exe, "-p", user_prompt,
                    "--model", self.model,
                    "--append-system-prompt-file", str(specf),
                    "--allowed-tools", "none",       # single-shot: no tools, one turn
                    "--setting-sources", "",         # drop operator hooks/skills/plugins
                    "--output-format", "json"]
            # The Windows `claude.CMD` shim launch is occasionally flaky ("The batch file
            # cannot be found" - an AV/cmd race that aborts BEFORE any model call, so a
            # failed launch is never billed). Retry the launch; returncode 0 means the
            # model ran, so a success is never re-billed.
            for attempt in range(3):
                proc = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                                      capture_output=True, text=True, encoding="utf-8",
                                      timeout=C.CLI_TIMEOUT_S)
                if proc.returncode == 0:
                    break
                time.sleep(2 * (attempt + 1))
        if proc.returncode != 0:
            raise RuntimeError(
                f"claude CLI exit {proc.returncode} after retries: "
                f"{(proc.stderr or '')[-400:]}")
        d = json.loads(proc.stdout)
        if d.get("is_error"):
            raise RuntimeError(f"claude CLI error: {str(d.get('result', ''))[:300]}")
        u = d.get("usage", {}) or {}
        # Claude Code may bill a tiny auxiliary model (e.g. haiku, ~20 tok) for internal
        # orchestration; the circuit generator is the model with the real output volume.
        mu = d.get("modelUsage", {}) or {}
        gen_model = (max(mu, key=lambda m: (mu[m].get("outputTokens")
                                            or mu[m].get("output_tokens") or 0))
                     if mu else self.model)
        return {
            "raw_output": d.get("result", "") or "",
            "latency_s": round(time.time() - t0, 3),
            "tokens_in": (u.get("input_tokens", 0)
                          + u.get("cache_creation_input_tokens", 0)
                          + u.get("cache_read_input_tokens", 0)),
            "tokens_out": u.get("output_tokens", 0),
            "cli_cost_usd": d.get("total_cost_usd", 0.0),
            "cli_model": gen_model,
            "cli_num_turns": d.get("num_turns"),
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


# ── Local: untrained-base control, single-shot via vLLM ───────────────────────

class LocalSingleShotAdapter:
    """A local HF model run SINGLE-SHOT (pass@1): one greedy generation on the
    byte-identical system + user prompt, verified in stage 2 - NO T5, NO ERC loop,
    NO killswitch. Same harness as the hosted legs, so the untrained-base-vs-trained
    read is apples-to-apples (isolates the 8B base from our training + pipeline).

    Backed by vLLM (paged attention): the ~6k-token system prompt + 8B in fp16 fits
    on commodity 2x16GB where the HF sdpa path OOMs. Tensor-parallel auto-scales to
    the visible GPUs (1 on an A40 box, 2 on a dual-T4)."""

    def __init__(self, cfg: dict):
        import torch
        from inference.vllm_backend import VLLMChatModel
        # fp16 not bf16: Turing-class GPUs (T4, sm_75) have no bf16, and fp16 is
        # inference-lossless for this read. enforce_eager dodges CUDA-graph capture
        # OOM on small VRAM. max_model_len covers the ~6.5k prompt + 4096 generation.
        self.gen = VLLMChatModel(
            cfg["qwen_model"], max_model_len=12288,
            tensor_parallel=max(1, torch.cuda.device_count()),
            dtype="float16", gpu_mem_util=0.90, enforce_eager=True)

    def run(self, system_prompt: str, user_prompt: str) -> dict:
        t0 = time.time()
        out = self.gen.generate(
            [[{"role": "system", "content": system_prompt},
              {"role": "user", "content": user_prompt}]],
            greedy=True, max_tokens=C.MAX_TOKENS)
        text = out[0][0] if (out and out[0]) else ""
        return {"raw_output": text, "latency_s": round(time.time() - t0, 3),
                "tokens_in": 0, "tokens_out": 0}


def build_adapter(model_name: str, suite: str):
    cfg = C.model_cfg(model_name)
    kind = cfg["adapter"]
    if kind == "claude_cli":
        return ClaudeCliAdapter(cfg["model"])
    if kind == "ohmatic":
        # T5 only for realuser (raw messy input). Holdout prompts are already
        # normalized - pass-through there, same as prod_eval.
        return OhmaticAdapter(cfg, use_t5=(suite == "realuser"))
    if kind == "local1shot":
        return LocalSingleShotAdapter(cfg)
    raise SystemExit(f"Unknown adapter kind: {kind}")
