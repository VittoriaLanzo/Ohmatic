"""Single source of truth for the T5 normalizer contract.

Imported by data-build, train, and inference so they can never drift. Locked:
  - T5 OUTPUT format == Qwen INPUT format: freeform normalized NL. Do NOT use the
    structured `t5_helper_target` intent format; Qwen was trained on freeform NL.
  - Scope: ENGLISH ONLY (see looks_non_english).
"""
from __future__ import annotations
import re

# Canonical task prefix. The 75k training rows use exactly this string; never
# change without rebuilding the dataset. (teacher_corpus's `t5_task_prefix`
# field is stale and IGNORED; this constant wins.)
T5_TASK_PREFIX = "normalize circuit description: "


def add_prefix(text: str) -> str:
    """Prepend the canonical task prefix to a raw user request."""
    return f"{T5_TASK_PREFIX}{text.strip()}"


def strip_prefix(text: str) -> str:
    return text[len(T5_TASK_PREFIX):] if text.startswith(T5_TASK_PREFIX) else text


# Entity extraction for the faithfulness gate + training eval metric.
# Specifics that MUST survive normalization; the gate fires only when the user
# gave specifics (clueless inputs have none to preserve).
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
    """3v counts as preserved if output has 3 or 3.3 (colloquial rounding)."""
    if v in out_volts:
        return True
    head = v.split(".")[0]
    return any(o == head or o.split(".")[0] == head for o in out_volts)


def faithfulness(src: str, out: str) -> tuple[float, dict[str, set[str]]]:
    """Fraction of `src` specifics surviving into `out`. Returns (ratio, missing-by-kind);
    ratio = preserved / total_src_entities, 1.0 when src has no specifics."""
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
    """Flag input that is mostly non-Latin script (CJK, Cyrillic, Arabic). English-only
    is a scope limit; this catches obvious out-of-scope cases."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    non_latin = sum(1 for c in letters if ord(c) > 0x024F)  # beyond Latin Extended-A
    return non_latin / len(letters) > 0.30


# ── Request-preservation guard (subject drift) ────────────────────────────────
# T5's ONLY job is to feed Qwen a cleaner version of the SAME request. On
# out-of-distribution prompts it can silently swap the circuit for a memorized one.
# subject_recall measures how much of the request's SUBJECT (its circuit-concept
# words) survives; the caller falls back to the raw prompt when too little does.
# Numeric specifics (volts/values/part numbers) are deliberately excluded here --
# those are the faithfulness() gate's job.

REQUEST_RECALL_MIN = 0.34  # >= ~1/3 of the request's subject words must survive

_SALIENT_STOP = frozenset("""
a an and or but the this that these those for to of in on at by with from into onto off
i we you it its my our me your is are be am was were do does did will would can could should
need needs want wants make makes made build builds design designs create creates please let
circuit circuits board boards schematic schematics thing things stuff something anything
some any use uses using used get gets got how many much more maybe idk lil little simple
just about basically really actually kind sort
""".split())

# Light synonym/abbreviation folding so faithful rephrasings are not punished.
_SYN = {"reg": "regul", "regulator": "regul", "regulate": "regul", "ldo": "regul",
        "photoresistor": "ldr", "photocell": "ldr"}


def _stem(tok: str) -> str:
    for suf in ("ing", "ers", "er", "ed", "es", "s"):
        if len(tok) > len(suf) + 2 and tok.endswith(suf):
            return tok[: -len(suf)]
    return tok


def _subject_tokens(text: str) -> set[str]:
    """Salient circuit-CONCEPT words: drop the task prefix, filler, short tokens, and
    any token containing a digit (volts/values/part numbers are faithfulness()'s job).
    Light-stem + fold a few synonyms so legitimate rephrasings are not penalised."""
    out: set[str] = set()
    for tok in re.findall(r"[a-z0-9]+", strip_prefix(text).lower()):
        if len(tok) < 3 or tok in _SALIENT_STOP or any(c.isdigit() for c in tok):
            continue
        tok = _SYN.get(tok, tok)
        tok = _stem(tok)
        out.add(_SYN.get(tok, tok))
    return out


def _matches(tok: str, others: set[str]) -> bool:
    """Token overlap tolerant of light stemming gaps (decoupl~decouple, regul~regulator):
    exact, or a >=4-char shared prefix in either direction."""
    if tok in others:
        return True
    if len(tok) >= 4:
        return any(len(o) >= 4 and (o.startswith(tok) or tok.startswith(o)) for o in others)
    return False


def subject_recall(src: str, out: str) -> float:
    """Fraction of the request's subject words that survive into `out`. Returns 1.0
    when the request has no subject words to preserve (e.g. a pure-numeric prompt)."""
    s = _subject_tokens(src)
    if not s:
        return 1.0
    o = _subject_tokens(out)
    return sum(1 for t in s if _matches(t, o)) / len(s)
