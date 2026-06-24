"""Cross-model benchmark config and reproducibility pins.

Everything defining a run lives here: model matrix, suites, decoding params,
artifact revisions. Reproduce = same commit + HF_TOKEN + one
`python -m eval.benchmark.cross_model.generate --model X --suite Y` per leg.

The competitor leg (codex) is PRODUCT-vs-PRODUCT, not model-vs-model: each ask
spins up a fresh, zero-context product instance via its own CLI (the shipped
product, on its own system prompt) with the Ohmatic format spec appended on top.
That spec is what lets a chat model emit the circuit schema at all, so it levels
the field while still measuring product vs product - not a bare model behind an api
key. The CLI uses the machine's own subscription auth, so NO api key is needed. The
only secret is HF_TOKEN, read from env (gated weights / private data) - never here.
"""

from __future__ import annotations

import os
from pathlib import Path

HERE        = Path(__file__).resolve().parent
# RESULTS_DIR is env-overridable (OHMATIC_RESULTS_DIR) so concurrent shards on one box can each
# write to a PRIVATE results dir - two processes never append to one file, which avoids
# interleaving when rows are multi-KB (the base 1-shot leg stores the raw circuit in raw_output).
RESULTS_DIR = Path(os.environ.get("OHMATIC_RESULTS_DIR") or (HERE / "results"))  # stage-1 raw generations
VERIFIED_DIR = HERE / "verified"        # stage-2 outcomes (recomputable forever)
DATA_DIR    = HERE / "data"             # benchmark prompt sets / artifacts

# ── Reproducibility pins ──────────────────────────────────────────────────────
HF_DATASET_REPO   = "VittoriaLanzo/Ohmatic"
FORWARD_HOLDOUT   = "data/holdout_v1.jsonl"           # prompt, prompt_sha1, partition
CORRECTION_HOLDOUT = "data/holdout_loopback_v1.jsonl" # LOCAL-ONLY suite (proprietary)

OHMATIC_FINAL_REPO = "VittoriaLanzo/Ohmatic-Qwen3-8B"  # fully-merged bf16 + GGUF
OHMATIC_GGUF_Q4    = "Ohmatic-Qwen3-8B-Q4_K_M.gguf"   # distribution quant, ~4.7 GB
OHMATIC_GGUF_Q8    = "Ohmatic-Qwen3-8B-Q8_0.gguf"     # quality-ceiling quant, ~8.5 GB
T5_NORMALIZER      = "VittoriaLanzo/ohmatic-t5-normalizer"
QWEN_BASE          = "Qwen/Qwen3-8B"                   # the untrained base Ohmatic fine-tunes from

# Decoding - identical budget for every model. Local legs are GREEDY
# (deterministic); the CLI competitor leg runs the shipped product's own default
# decoding (the CLI exposes no sampling knob) - that IS the product, disclosed.
MAX_TOKENS    = 4096
TEMPERATURE   = 0.0
PIPELINE_MAX_RETRIES = 3          # Ohmatic product setting: 1 generate + 3 corrections

# CLI competitor-leg setting. No api key: the CLI uses the machine's own subscription
# auth. Cost is whatever the CLI reports per call (total_cost_usd), recorded verbatim
# in stage 1 - there is no static price table to drift.
CLI_TIMEOUT_S = 1200              # per-ask hard cap; a stuck call is skipped + resumed
                                  # (generous: codex at xhigh effort can take many minutes)

# Codex leg runs at MAX reasoning effort (xhigh) - the strongest setting the codex
# product offers, so the leg is the toughest possible competitor.
CODEX_REASONING_EFFORT = "xhigh"

# ── Model matrix ──────────────────────────────────────────────────────────────
# adapter: which client implementation runs the leg
#   "codex_cli" - a fresh zero-context `codex exec` per ask on the ChatGPT
#                 subscription (no api key), the Ohmatic spec in AGENTS.md,
#                 sandboxed read-only. Product-vs-product, not model-vs-model.
#   "ohmatic"   - the FULL product pipeline (T5 -> Qwen -> ERC -> retries ->
#                 killswitch), via inference.pipeline.OhmaticPipeline. Needs GPU.
# t5: the bench prompts are already normalized (forward holdout, correction, and the
#     pcbschemagen NL requests), so the pipeline runs with a pass-through normalizer
#     here (same convention as eval/benchmark/prod_eval.py).
MODELS: dict[str, dict] = {
    # Claude Opus, the off-box competitor driven product-vs-product through the `claude -p`
    # CLI (no api key) at MAX reasoning effort. `model` is the full pinned id so the leg is
    # reproducible; the CLI BINARY is itself pinned via OHMATIC_CLAUDE_BIN to a version whose
    # -p output is a raw single-shot JSON completion (newer CLIs emit agent prose) - see
    # ClaudeCliAdapter. A fresh, sealed, zero-context instance per ask.
    "opus": dict(
        adapter="claude_cli", model="claude-opus-4-8", effort="max",
        suites=["forward", "pcbschemagen"],
    ),

    # OpenAI Codex, the off-box competitor: `codex exec` on the local ChatGPT
    # subscription (no api key), the Ohmatic spec in AGENTS.md on top of Codex's
    # product prompt, at MAX reasoning effort (xhigh). model="" -> the CLI's
    # configured default (recorded via cli_model). A fresh zero-context instance per ask.
    "codex": dict(
        adapter="codex_cli", model="",
        suites=["forward", "pcbschemagen"],
    ),

    # Ohmatic product legs - full end-to-end pipeline incl. killswitch
    "bf16": dict(                    # the trained model, full-precision bf16
        adapter="ohmatic", qwen_model=OHMATIC_FINAL_REPO, backend="hf",
        # ~16 GB weights: needs 2xT4 (tensor-parallel) or an A100 - won't fit one 15 GB T4.
        suites=["forward", "correction", "pcbschemagen"],
    ),
    "q4": dict(                      # the distribution quant (Q4_K_M)
        adapter="ohmatic", gguf_repo=OHMATIC_FINAL_REPO, gguf_file=OHMATIC_GGUF_Q4,
        backend="llamacpp",
        suites=["forward", "correction", "pcbschemagen"],
    ),
    "q8": dict(                      # higher-fidelity quant (Q8_0) - the quality
        adapter="ohmatic", gguf_repo=OHMATIC_FINAL_REPO, gguf_file=OHMATIC_GGUF_Q8,
        backend="llamacpp",                  # ceiling for a single-GPU GGUF deploy
        suites=["forward", "correction", "pcbschemagen"],
    ),

    # Baseline: the UNTRAINED Qwen3-8B base (the model Ohmatic fine-tunes from) run SINGLE-SHOT
    # (pass@1) on the same C1 competitor prompt - no T5, no ERC loop, no killswitch. The
    # pre-fine-tune floor; isolates what the training + the pipeline add over the raw base model.
    "qwen3-base-1shot": dict(
        adapter="local1shot", qwen_model=QWEN_BASE, backend="hf",
        suites=["pcbschemagen"],
    ),
}

SUITES = ("forward", "correction", "pcbschemagen")

# Off-box models never see the correction suite (local-only).
LOCAL_ONLY_SUITES = ("correction",)


def model_cfg(name: str) -> dict:
    if name not in MODELS:
        raise SystemExit(f"Unknown model '{name}'. Known: {', '.join(MODELS)}")
    return MODELS[name]


def check_suite_allowed(model: str, suite: str) -> None:
    cfg = model_cfg(model)
    if suite not in cfg["suites"]:
        raise SystemExit(f"Suite '{suite}' not enabled for '{model}' "
                         f"(enabled: {cfg['suites']})")
    if suite in LOCAL_ONLY_SUITES and cfg["adapter"] != "ohmatic":
        raise SystemExit(f"Suite '{suite}' is LOCAL-ONLY (proprietary) - "
                         f"refusing to send it to an off-box model.")
