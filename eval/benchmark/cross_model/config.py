"""Cross-model benchmark config and reproducibility pins.

Everything defining a run lives here: model matrix, suites, decoding params,
artifact revisions. Reproduce = same commit + HF_TOKEN + one
`python -m eval.benchmark.cross_model.generate --model X --suite Y` per leg.

The Claude legs (fable-5, opus) are PRODUCT-vs-PRODUCT, not model-vs-model: each
ask spins up a fresh, zero-context Claude Code instance via the `claude -p` CLI
(the shipped product, on its own system prompt) with the Ohmatic format spec
appended on top. That spec is what lets a chat model emit the circuit schema at
all, so it levels the field while still measuring product vs product - not a bare
model behind an api key. The CLI uses the local Claude Code subscription auth, so
NO api key is needed (the earlier hosted-API framing was a fallacy). The only
secret is HF_TOKEN, read from env (gated weights / private data) - never here.
"""

from __future__ import annotations

from pathlib import Path

HERE        = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"          # stage-1 raw generations (append-only)
VERIFIED_DIR = HERE / "verified"        # stage-2 outcomes (recomputable forever)
DATA_DIR    = HERE / "data"             # realuser prompt set (committed)

# ── Reproducibility pins ──────────────────────────────────────────────────────
HF_DATASET_REPO   = "VittoriaLanzo/Ohmatic"
FORWARD_HOLDOUT   = "data/holdout_v1.jsonl"           # prompt, prompt_sha1, partition
CORRECTION_HOLDOUT = "data/holdout_loopback_v1.jsonl" # LOCAL-ONLY suite (proprietary)
REALUSER_FILE     = DATA_DIR / "realuser_prompts.jsonl"

OHMATIC_FINAL_REPO = "VittoriaLanzo/Ohmatic-Qwen3-8B"  # fully-merged bf16 + GGUF
OHMATIC_GGUF_Q4    = "Ohmatic-Qwen3-8B-Q4_K_M.gguf"   # distribution quant, ~4.7 GB
OHMATIC_GGUF_Q8    = "Ohmatic-Qwen3-8B-Q8_0.gguf"     # quality-ceiling quant, ~8.5 GB
T5_NORMALIZER      = "VittoriaLanzo/ohmatic-t5-normalizer"
QWEN_BASE          = "Qwen/Qwen3-8B"

# Decoding - identical budget for every model. Local legs are GREEDY
# (deterministic); the Claude CLI legs run the shipped product's own default
# decoding (the CLI exposes no sampling knob) - that IS the product, disclosed.
MAX_TOKENS    = 4096
TEMPERATURE   = 0.0
PIPELINE_MAX_RETRIES = 3          # Ohmatic product setting: 1 generate + 3 corrections

# Claude-CLI ("subagent") leg settings. No api key: the CLI uses the local Claude
# Code subscription auth. Cost is whatever the CLI reports per call (total_cost_usd),
# recorded verbatim in stage 1 - there is no static price table to drift.
CLI_TIMEOUT_S = 1200              # per-ask hard cap; a stuck call is skipped + resumed
                                  # (generous: codex at xhigh effort can take many minutes)

# Codex leg runs at MAX reasoning effort (xhigh) - the strongest setting the codex
# product offers, so the leg is the toughest possible competitor (disclosed: higher
# than the Claude legs' default effort, which only makes the Ohmatic margin conservative).
CODEX_REASONING_EFFORT = "xhigh"

# ── Model matrix ──────────────────────────────────────────────────────────────
# adapter: which client implementation runs the leg
#   "claude_cli"- a fresh zero-context Claude Code instance per ask via `claude -p`
#                 (subscription auth, NO api key); the Ohmatic format spec is appended
#                 on top of Claude's own product prompt. Single-shot, no tools - the
#                 shipped product, so this is product-vs-product not model-vs-model.
#   "codex_cli" - the OpenAI mirror of claude_cli: `codex exec` on the ChatGPT
#                 subscription (no api key), spec in AGENTS.md, sandboxed read-only.
#   "ohmatic"   - the FULL product pipeline (T5 -> Qwen -> ERC -> retries ->
#                 killswitch), via inference.pipeline.OhmaticPipeline. Needs GPU.
#   "local1shot"- a local HF model run SINGLE-SHOT via vLLM (pass@1, no pipeline):
#                 the untrained-base control, same harness as the Claude legs.
# t5: realuser suite only - forward/correction holdout prompts are already
#     normalized, so the pipeline runs with a pass-through normalizer there
#     (same convention as eval/benchmark/prod_eval.py).
MODELS: dict[str, dict] = {
    # Claude products, subagent-driven (forward + realuser; correction is local-only).
    # adapter="claude_cli": a fresh zero-context `claude -p` instance per ask with the
    # Ohmatic spec appended on top of Claude's product prompt. `model` is the CLI's
    # pinned id (full id, not an alias, so the leg is reproducible).
    # effort: every frontier leg runs at its product's MAX reasoning effort so the
    # comparison is fair and the competitor is as strong as possible. Claude's ceiling
    # is "max" (above "xhigh"); fable-5 is pinned to "xhigh" to match the effort its
    # published run actually used (a subagent run that preserved that setting).
    "fable-5": dict(
        adapter="claude_cli", model="claude-fable-5", effort="xhigh",
        suites=["forward", "realuser", "pcbschemagen"],
    ),
    # NOTE: the `realuser` suite was AUTHORED by Claude Opus (see fairness contract).
    # Opus therefore evaluates realuser on home turf - a conservative bias FAVORING the
    # Claude leg; `forward` (held-out, not Opus-authored) is the contamination-free read.
    "opus": dict(
        adapter="claude_cli", model="claude-opus-4-8", effort="max",
        suites=["forward", "realuser", "pcbschemagen"],
    ),
    # OpenAI Codex, the mirror of the Claude legs: `codex exec` on the local ChatGPT
    # subscription (no api key), Ohmatic spec in AGENTS.md on top of Codex's product
    # prompt. model="" -> the Codex CLI's configured default (recorded via cli_model).
    "codex": dict(
        adapter="codex_cli", model="",
        suites=["forward", "realuser", "pcbschemagen"],
    ),

    # Ohmatic product legs - full end-to-end pipeline incl. killswitch
    "qwen3-base": dict(                      # untrained base in the SAME shell
        adapter="ohmatic", qwen_model=QWEN_BASE, backend="hf",
        suites=["forward", "realuser", "correction"],
    ),
    "qwen3-base-1shot": dict(                # untrained base, SINGLE-SHOT (pass@1):
        adapter="local1shot", qwen_model=QWEN_BASE,   # same harness as the hosted
        suites=["realuser"],                # legs - isolates the base from training
    ),
    "bf16": dict(                    # the trained model, full-precision bf16
        adapter="ohmatic", qwen_model=OHMATIC_FINAL_REPO, backend="hf",
        # ~16 GB weights: needs 2xT4 (tensor-parallel) or an A100 - won't fit one 15 GB T4.
        suites=["forward", "realuser", "correction", "pcbschemagen"],
    ),
    "q4": dict(                      # the distribution quant (Q4_K_M)
        adapter="ohmatic", gguf_repo=OHMATIC_FINAL_REPO, gguf_file=OHMATIC_GGUF_Q4,
        backend="llamacpp",
        suites=["forward", "realuser", "correction", "pcbschemagen"],
    ),
    "q8": dict(                      # higher-fidelity quant (Q8_0) - the quality
        adapter="ohmatic", gguf_repo=OHMATIC_FINAL_REPO, gguf_file=OHMATIC_GGUF_Q8,
        backend="llamacpp",                  # ceiling for a single-GPU GGUF deploy
        suites=["forward", "realuser", "correction", "pcbschemagen"],
    ),

    # Ablation: trained model WITHOUT the T5 front-end (realuser only) -
    # isolates exactly what T5 contributes on messy input.
    "noT5": dict(
        adapter="ohmatic", qwen_model=OHMATIC_FINAL_REPO, backend="hf",
        no_t5=True,
        suites=["realuser"],
    ),
}

SUITES = ("forward", "realuser", "correction", "pcbschemagen")

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
    if suite in LOCAL_ONLY_SUITES and cfg["adapter"] not in ("ohmatic", "local1shot"):
        raise SystemExit(f"Suite '{suite}' is LOCAL-ONLY (proprietary) - "
                         f"refusing to send it to an off-box model.")
