"""
Cross-model benchmark - suite loaders.
=======================================
Uniform item shape across all three suites:
    {"prompt_id": str, "suite": str, "user_prompt": str,
     "category": str,            # partition / break-category / realuser category
     "system_extra": str}        # correction suite only: the broken circuit +
                                 # ERC feedback turn (NEVER leaves local legs)
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
    """Frozen held-out forward set (HF, private). Deterministic order +
    partition-proportional subsetting - same convention as prod_eval."""
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


def load_realuser() -> list[dict]:
    """Novel messy 'real user' prompts - authored by a NEUTRAL model (Opus,
    not in the matrix), dedup-checked against the training corpus, committed
    to the repo so the suite is frozen and citable."""
    if not C.REALUSER_FILE.exists():
        raise SystemExit(f"{C.REALUSER_FILE} missing - run the Opus prompt-"
                         f"authoring step first (see README).")
    rows = [json.loads(l) for l in C.REALUSER_FILE.read_text(encoding="utf-8")
            .splitlines() if l.strip()]
    return [{"prompt_id": r.get("id") or _sha1(r["prompt"]),
             "suite": "realuser",
             "user_prompt": r["prompt"],
             "category": r.get("category", "?"),
             "system_extra": ""} for r in rows]


def load_correction(per_category: int = 0) -> list[dict]:
    """Held-out ERC-repair cases (LOCAL legs only - enforced in config).

    Real holdout_loopback_v1 row schema (validated against the live file):
        signature        stable row id
        rule             break category (e.g. POWER_IC_MISSING_BYPASS_CAPACITOR)
        input_messages   the FULL trained conversation (system + broken circuit
                         + ERC feedback) - passed to the generator VERBATIM
        reference_fixed  reference repair (not used for scoring; ERC is the judge)

    Correction is a SINGLE-SHOT repair task (mirrors in-training correction_eval):
    the item carries `messages` and generate.py routes it straight to the
    generator's chat() - no T5, no retry loop."""
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


def load_suite(suite: str, n: int = 0) -> list[dict]:
    if suite == "forward":
        return load_forward(n)
    if suite == "realuser":
        items = load_realuser()
        return items[:n] if n else items
    if suite == "correction":
        return load_correction(per_category=n or 0)
    raise SystemExit(f"Unknown suite '{suite}'")
