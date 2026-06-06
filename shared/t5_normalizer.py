"""Single source of truth for the T5 normalizer contract.

Imported by ALL three sites so train/serve/data-build can never drift:
  - dataset/scripts/build_t5_training_jsonl.py   (builds inputs with the prefix)
  - train/finetune_t5.py                          (eval metric: entity preservation)
  - inference/pipeline.py                          (prefix + the hard faithfulness gate)

Design decisions locked here (see also OHMATIC_HANDOFF.md):
  - T5 OUTPUT format == Qwen INPUT format: freeform normalized NL (the "normal" precision
    prompt). We deliberately do NOT use the structured `t5_helper_target` intent format —
    Qwen was trained on freeform normalized NL, so that is the contract.
  - Scope: ENGLISH ONLY (see looks_non_english). Non-English is out of scope for now.
"""
from __future__ import annotations
import re

# THE canonical task prefix. The 75k training rows already use exactly this string; never
# change it without rebuilding the dataset. (NB: teacher_corpus records carry a stale
# `t5_task_prefix` field — it is IGNORED; this constant wins.)
T5_TASK_PREFIX = "normalize circuit description: "


def add_prefix(text: str) -> str:
    """Prepend the canonical task prefix to a raw user request."""
    return f"{T5_TASK_PREFIX}{text.strip()}"


def strip_prefix(text: str) -> str:
    return text[len(T5_TASK_PREFIX):] if text.startswith(T5_TASK_PREFIX) else text


# ── Entity extraction (for the faithfulness gate + the training eval metric) ──────────
# Specifics a user might state that MUST survive normalization. Clueless inputs contain
# none of these (nothing to preserve); the gate only fires when the user DID give specifics.
_RE_VOLT = re.compile(r"\b(\d+(?:\.\d+)?)\s?v\b", re.I)
_RE_PART = re.compile(r"\b([A-Za-z]{2,}\d{2,}[A-Za-z0-9-]*|555)\b")          # AMS1117, NE5532, RS485, nRF52…
_RE_VALUE = re.compile(r"\b(\d+(?:\.\d+)?)\s?(k|m)?(ohm|Ω|uf|nf|pf|µf|mh|uh|h)\b", re.I)


def extract_entities(text: str) -> dict[str, set[str]]:
    """Return {'volts','parts','values'} sets of normalized entity strings found in text."""
    volts = {m.group(1) for m in _RE_VOLT.finditer(text)}
    parts = {m.group(1).lower() for m in _RE_PART.finditer(text)}
    values = {("".join(g for g in m.groups() if g)).lower().replace(" ", "")
              for m in _RE_VALUE.finditer(text)}
    return {"volts": volts, "parts": parts, "values": values}


def _volt_ok(v: str, out_volts: set[str]) -> bool:
    """3v should count as preserved if output has 3 or 3.3 (colloquial rounding)."""
    if v in out_volts:
        return True
    head = v.split(".")[0]
    return any(o == head or o.split(".")[0] == head for o in out_volts)


def faithfulness(src: str, out: str) -> tuple[float, dict[str, set[str]]]:
    """How many specifics in `src` survive into `out`. Returns (ratio, missing-by-kind).
    ratio = preserved / total_src_entities; 1.0 when src has no specifics (clueless input)."""
    s = extract_entities(src)
    o = extract_entities(out)
    missing: dict[str, set[str]] = {"volts": set(), "parts": set(), "values": set()}
    total = preserved = 0
    for v in s["volts"]:
        total += 1
        if _volt_ok(v, o["volts"]):
            preserved += 1
        else:
            missing["volts"].add(v)
    for kind in ("parts", "values"):
        for e in s[kind]:
            total += 1
            if e in o[kind]:
                preserved += 1
            else:
                missing[kind].add(e)
    ratio = 1.0 if total == 0 else preserved / total
    return ratio, missing


def looks_non_english(text: str) -> bool:
    """Light heuristic: flag input that is mostly non-Latin script (CJK, Cyrillic, Arabic…).
    English-only is a documented scope limit; this catches the obvious out-of-scope cases."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    non_latin = sum(1 for c in letters if ord(c) > 0x024F)  # beyond Latin Extended-A
    return non_latin / len(letters) > 0.30
