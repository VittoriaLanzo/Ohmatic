"""
upload_holdout_to_hf.py — Push the frozen held-out benchmark to HF (PRIVATE)
=============================================================================
The benchmark data is moat: prompts + reference circuits derived from the private
dataset. It is gitignored locally and lives ONLY on the private HF dataset repo,
alongside the training data. The training pod pulls the exclude files from here to
guarantee it never trains on benchmark prompts.

Uploads (to data/ in VittoriaLanzo/Ohmatic, private):
  holdout_v1.jsonl               benchmark prompts + reference circuits
  holdout_exclude_hashes.txt     forward prompt hashes to exclude from training
  holdout_loopback_v1.jsonl      ERC-repair holdout cases
  holdout_exclude_loopback.txt   loopback row signatures to exclude
  holdout_manifest.json          provenance

Run build_holdout.py FIRST. Repo stays PRIVATE — never set private=False.

Usage:
  python eval/benchmark/upload_holdout_to_hf.py
  python eval/benchmark/upload_holdout_to_hf.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT     = Path(__file__).resolve().parents[2]
BENCH    = ROOT / "eval" / "benchmark"
ENV_FILE = ROOT / ".env"

FILES = [
    ("holdout_v1.jsonl",             "data/holdout_v1.jsonl"),
    ("holdout_exclude_hashes.txt",   "data/holdout_exclude_hashes.txt"),
    ("holdout_loopback_v1.jsonl",    "data/holdout_loopback_v1.jsonl"),
    ("holdout_exclude_loopback.txt", "data/holdout_exclude_loopback.txt"),
    ("holdout_manifest.json",        "data/holdout_manifest.json"),
]


def _load_env() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    _load_env()
    token   = os.environ.get("HF_TOKEN", "")
    repo_id = os.environ.get("HF_REPO_ID", "VittoriaLanzo/Ohmatic")

    missing = [name for name, _ in FILES if not (BENCH / name).exists()]
    if missing:
        print("ERROR: missing benchmark files (run build_holdout.py first):", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        sys.exit(1)

    print(f"Target: https://huggingface.co/datasets/{repo_id}  (PRIVATE)\n")
    for name, repo_path in FILES:
        size = (BENCH / name).stat().st_size
        print(f"  {name:32s} {size:>8,} B  ->  {repo_path}")
    print()

    if args.dry_run:
        print("[dry-run] nothing uploaded.")
        return

    if not token:
        print("ERROR: HF_TOKEN not set (add to .env).", file=sys.stderr)
        sys.exit(1)

    from huggingface_hub import HfApi
    api = HfApi(token=token)
    api.create_repo(repo_id=repo_id, repo_type="dataset", private=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for name, repo_path in FILES:
        print(f"  uploading {name} ...", end=" ", flush=True)
        api.upload_file(
            path_or_fileobj=str(BENCH / name),
            path_in_repo=repo_path,
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"holdout benchmark: {name} ({ts})",
        )
        print("OK")
    print(f"\nDone. Benchmark on HF (private): {repo_id}/data/")


if __name__ == "__main__":
    main()
