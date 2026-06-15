"""Cross-model benchmark config and reproducibility pins.

Everything defining a run lives here: model matrix, suites, decoding params,
artifact revisions. Reproduce = same commit + the three env keys + one
`python -m eval.benchmark.cross_model.generate --model X --suite Y` per leg.

Secrets live ONLY in env, never here: ANTHROPIC_API_KEY (Fable), OPENAI_API_KEY
(Codex, + optional OPENAI_BASE_URL / OPENAI_MODEL), HF_TOKEN (private HF repos).
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
OHMATIC_GGUF_Q4    = "Ohmatic-Qwen3-8B-Q4_K_M.gguf"
T5_NORMALIZER      = "VittoriaLanzo/ohmatic-t5-normalizer"
QWEN_BASE          = "Qwen/Qwen3-8B"

# Decoding - identical budget for every model. Local legs are GREEDY
# (deterministic); hosted legs are temperature-pinned where the API allows
# (adaptive models that reject sampling params run at their default - disclosed).
MAX_TOKENS    = 4096
TEMPERATURE   = 0.0
PIPELINE_MAX_RETRIES = 3          # Ohmatic product setting: 1 generate + 3 corrections

# Hosted-API price table, USD per MTok (input, output) - for the cost column.
PRICES = {
    "fable-5":   (10.0, 50.0),
    "codex-5.5": (1.25, 10.0),    # adjust to the configured OpenAI model's sheet
}

# ── Model matrix ──────────────────────────────────────────────────────────────
# adapter: which client implementation runs the leg
#   "anthropic" - Anthropic SDK (hosted)
#   "openai"    - OpenAI-compatible client (hosted Codex OR any base_url)
#   "ohmatic"   - the FULL product pipeline (T5 -> Qwen -> ERC -> retries ->
#                 killswitch), via inference.pipeline.OhmaticPipeline. Needs GPU.
#   "local1shot"- a local HF model run SINGLE-SHOT via vLLM (pass@1, no pipeline):
#                 the untrained-base control, same harness as the hosted legs.
# t5: realuser suite only - forward/correction holdout prompts are already
#     normalized, so the pipeline runs with a pass-through normalizer there
#     (same convention as eval/benchmark/prod_eval.py).
MODELS: dict[str, dict] = {
    # Hosted frontier (forward + realuser only; correction suite is local-only IP)
    "fable-5": dict(
        adapter="anthropic", model="claude-fable-5",
        suites=["forward", "realuser"],
    ),
    "codex-5.5": dict(
        adapter="openai", model="env:OPENAI_MODEL",   # resolved at runtime
        suites=["forward", "realuser"],
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
    "star-r2-bf16": dict(                    # the trained model, bf16
        adapter="ohmatic", qwen_model=OHMATIC_FINAL_REPO, backend="hf",
        suites=["forward", "realuser", "correction"],
    ),
    "star-r2-q4": dict(                      # the distribution quant
        adapter="ohmatic", gguf_repo=OHMATIC_FINAL_REPO, gguf_file=OHMATIC_GGUF_Q4,
        backend="llamacpp",
        suites=["forward", "realuser", "correction"],
    ),

    # Ablation: trained model WITHOUT the T5 front-end (realuser only) -
    # isolates exactly what T5 contributes on messy input.
    "star-r2-noT5": dict(
        adapter="ohmatic", qwen_model=OHMATIC_FINAL_REPO, backend="hf",
        no_t5=True,
        suites=["realuser"],
    ),
}

SUITES = ("forward", "realuser", "correction")

# Hosted APIs never see the correction suite (proprietary ERC feedback corpus).
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
    if suite in LOCAL_ONLY_SUITES and cfg["adapter"] in ("anthropic", "openai"):
        raise SystemExit(f"Suite '{suite}' is LOCAL-ONLY (proprietary) - "
                         f"refusing to send it to a hosted API.")
