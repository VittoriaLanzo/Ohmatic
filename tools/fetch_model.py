"""Tier-aware model fetcher: downloads the weights the doctor recommended.

    ./ohmatic fetch              # uses .ohmatic-run/doctor.json (auto-written by start/doctor)
    ./ohmatic fetch --tier q8_0  # override
    ./ohmatic fetch --dry-run    # plan only: artifact, size, disk check, no download

Weights land in ./models/ (gitignored); ./models/active.json records what's
installed so the inference pipeline can pick it up. Downloads resume on
interruption (huggingface_hub). While the repos are private, HF_TOKEN must be
set; after the public launch, anonymous downloads work.
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Windows without admin/Developer Mode cannot create the HF cache symlinks
# (WinError 1314). Copying files instead works everywhere.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# The GGUF path builds its prompt with the model's HF tokenizer (enable_thinking=False),
# so the GGUF tiers must fetch the tokenizer too - not just the .gguf.
_TOKENIZER_FILES = ["tokenizer.json", "tokenizer_config.json", "vocab.json",
                    "merges.txt", "special_tokens_map.json", "added_tokens.json",
                    "chat_template.jinja", "generation_config.json"]

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
DOCTOR = ROOT / ".ohmatic-run" / "doctor.json"

REPO = "VittoriaLanzo/Ohmatic-Qwen3-8B"
T5_REPO = "VittoriaLanzo/ohmatic-t5-normalizer"

# tier -> (kind, files, approx GB needed incl. headroom)
PLANS: dict[str, dict] = {
    "bf16":       {"kind": "snapshot", "exclude": ["*.gguf"], "gb": 20.0,
                   "note": "full bf16 safetensors (GPU, transformers/vLLM)"},
    "q8_0":       {"kind": "file", "file": "Ohmatic-Qwen3-8B-Q8_0.gguf", "gb": 10.5,
                   "note": "near-lossless GGUF (GPU via llama.cpp, or Apple Metal)"},
    "q4_k_m":     {"kind": "file", "file": "Ohmatic-Qwen3-8B-Q4_K_M.gguf", "gb": 6.5,
                   "note": "4-bit GGUF (GPU via llama.cpp, or Apple Metal)"},
    "q4_k_m_cpu": {"kind": "file", "file": "Ohmatic-Qwen3-8B-Q4_K_M.gguf", "gb": 6.5,
                   "note": "4-bit GGUF, CPU inference in system RAM (slow)"},
}


def recommended_tier() -> str:
    if DOCTOR.exists():
        try:
            return json.loads(DOCTOR.read_text(encoding="utf-8")).get("recommended_model", "stub")
        except Exception:
            pass
    return "stub"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="", choices=["", *PLANS, "stub"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--with-t5", action="store_true", default=True,
                    help="also fetch the T5 normalizer (~1 GB; default on)")
    args = ap.parse_args()

    tier = args.tier or recommended_tier()
    if tier == "stub" or tier not in PLANS:
        print(f"tier '{tier}': no local weights needed (stub/cloud mode). "
              f"Run './ohmatic doctor' or pass --tier explicitly.")
        return 0

    plan = PLANS[tier]
    free_gb = shutil.disk_usage(ROOT).free / 1e9
    print(f"tier      {tier} - {plan['note']}")
    print(f"artifact  {REPO}" + (f" :: {plan['file']}" if plan["kind"] == "file" else " (snapshot, GGUFs excluded)"))
    print(f"disk      need ~{plan['gb']:.0f} GB free, have {free_gb:.0f} GB")
    if free_gb < plan["gb"]:
        print("ERROR: not enough disk space.", file=sys.stderr)
        return 1
    token = os.environ.get("HF_TOKEN") or None
    print(f"auth      {'HF_TOKEN set' if token else 'anonymous (fails while the repo is private)'}")
    if args.dry_run:
        print("dry-run: nothing downloaded.")
        return 0

    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except ImportError:
        print("ERROR: pip install huggingface_hub", file=sys.stderr)
        return 1

    MODELS.mkdir(exist_ok=True)
    tokenizer_path = ""
    if plan["kind"] == "file":
        path = hf_hub_download(REPO, plan["file"], token=token,
                               local_dir=MODELS, local_dir_use_symlinks=False)
        # GGUF tiers ship only the .gguf - fetch the tokenizer for enable_thinking=False.
        tok_dir = MODELS / "Ohmatic-Qwen3-8B-tokenizer"
        snapshot_download(REPO, token=token, allow_patterns=_TOKENIZER_FILES,
                          local_dir=tok_dir, local_dir_use_symlinks=False)
        tokenizer_path = str(tok_dir)
    else:
        path = snapshot_download(REPO, token=token, ignore_patterns=plan["exclude"],
                                 local_dir=MODELS / "Ohmatic-Qwen3-8B",
                                 local_dir_use_symlinks=False)
        tokenizer_path = str(path)  # full snapshot already includes the tokenizer
    t5_path = ""
    if args.with_t5:
        t5_path = snapshot_download(T5_REPO, token=token, local_dir=MODELS / "t5-normalizer",
                                    local_dir_use_symlinks=False)

    (MODELS / "active.json").write_text(json.dumps(
        {"tier": tier, "model_path": str(path), "t5_path": t5_path,
         "tokenizer_path": tokenizer_path, "repo": REPO},
        indent=2), encoding="utf-8")
    print(f"\ninstalled -> {path}")
    print(f"manifest  -> {MODELS / 'active.json'}")
    print("Run the real pipeline with:  python -m inference.cli \"<prompt>\" "
          f"--t5-model \"{t5_path or T5_REPO}\" --qwen-model \"{path}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
