"""Cross-model benchmark suite loaders.

Uniform item shape across all three suites:
    {"prompt_id": str, "suite": str, "user_prompt": str,
     "category": str,        # partition / category
     "system_extra": str}    # correction suite only (NEVER leaves local legs)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval.benchmark.cross_model import config as C


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _hf_jsonl(filename: str) -> list[dict]:
    from huggingface_hub import hf_hub_download
    p = hf_hub_download(C.HF_DATASET_REPO, filename, repo_type="dataset",
                        token=os.environ.get("HF_TOKEN"))
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def load_forward(n: int = 0) -> list[dict]:
    """Frozen held-out forward set (private HF). Deterministic order, partition-
    proportional subsetting (same convention as prod_eval)."""
    rows = _hf_jsonl(C.FORWARD_HOLDOUT)
    rows.sort(key=lambda r: r.get("prompt_sha1", r["prompt"]))
    if n and n < len(rows):
        from collections import defaultdict
        by = defaultdict(list)
        for r in rows:
            by[r.get("partition", "?")].append(r)
        out = []
        for part in sorted(by):
            grp = by[part]
            out.extend(grp[:max(1, round(n * len(grp) / len(rows)))])
        rows = out[:n]
    return [{"prompt_id": r.get("prompt_sha1") or _sha1(r["prompt"]),
             "suite": "forward",
             "user_prompt": r["prompt"],
             "category": r.get("partition", "?"),
             "system_extra": ""} for r in rows]


def load_correction(per_category: int = 0) -> list[dict]:
    """Held-out ERC-repair cases (LOCAL legs only, enforced in config).

    Each item carries its conversation turns in `messages`; generate.py routes it
    straight to chat() - single-shot, no T5, no retry loop - and the output is
    verified in stage 2 like any other generation."""
    rows = _hf_jsonl(C.CORRECTION_HOLDOUT)
    if per_category:
        from collections import defaultdict
        by = defaultdict(list)
        for r in rows:
            by[r.get("rule", "?")].append(r)
        rows = [r for cat in sorted(by) for r in by[cat][:per_category]]
    return [{"prompt_id": r["signature"][:16],
             "suite": "correction",
             "user_prompt": "",
             "category": r.get("rule", "?"),
             "system_extra": "",
             "messages": r["input_messages"]} for r in rows]


def load_pcbschemagen() -> list[dict]:
    """PCBBench single-circuit tasks (MIT, github.com/HZou9/PCBSchemaGen_v2) rendered as
    functional NL requests. Third-party generalization probe, scored with OUR ERC.
    The suite is materialised from source (not committed, to avoid redistributing their
    data without their notice) - run make_pcbschemagen_suite first."""
    f = C.DATA_DIR / "pcbschemagen_prompts.jsonl"
    if not f.exists():
        raise SystemExit(f"{f} missing - build it first:\n"
                         f"  python -m eval.benchmark.cross_model.make_pcbschemagen_suite")
    rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [{"prompt_id": r["id"], "suite": "pcbschemagen",
             "user_prompt": r["prompt"], "category": r.get("category", "?"),
             "system_extra": ""} for r in rows]


def load_suite(suite: str, n: int = 0) -> list[dict]:
    if suite == "forward":
        return load_forward(n)
    if suite == "correction":
        return load_correction(per_category=n or 0)
    if suite == "pcbschemagen":
        items = load_pcbschemagen()
        return items[:n] if n else items
    raise SystemExit(f"Unknown suite '{suite}'")
