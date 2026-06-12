"""Freeze a held-out benchmark the model never trains on, so post-training ERC
pass-rates are honest and third-party reproducible.

Two partitions: unseen_variant (held-out specs from trained families) and
novel_family (entire families removed from training; the grokking proof).

Outputs (eval/benchmark/): holdout_v1.jsonl, holdout_exclude_hashes.txt,
holdout_loopback_v1.jsonl, holdout_exclude_loopback.txt, holdout_manifest.json.

finetune_runpod.py reads the two exclude files and drops matching rows,
GUARANTEEING zero overlap. Run this BEFORE training, commit the frozen files,
and never regenerate for a given model release.

    python eval/benchmark/build_holdout.py [--verify-only]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from eval.diagnostics import analyze_schematic

# ── Paths ───────────────────────────────────────────────────────────────────
DATA_DIR      = ROOT / "dataset" / "generated"
FORWARD_SRC   = DATA_DIR / "qwen_training_all.jsonl"
LOOPBACK_SRC  = DATA_DIR / "erc_loopback_all.jsonl"

OUT_DIR       = ROOT / "eval" / "benchmark"
OUT_BENCH     = OUT_DIR / "holdout_v1.jsonl"
OUT_EXCLUDE   = OUT_DIR / "holdout_exclude_hashes.txt"
OUT_LB_BENCH  = OUT_DIR / "holdout_loopback_v1.jsonl"
OUT_LB_EXCL   = OUT_DIR / "holdout_exclude_loopback.txt"
OUT_MANIFEST  = OUT_DIR / "holdout_manifest.json"

# ── Knobs ───────────────────────────────────────────────────────────────────
SEED                    = 1234     # distinct from the training shuffle seed (42)
TARGET_UNSEEN_VARIANT   = 128      # in-distribution held-out prompts
MAX_PROMPTS_PER_FAMILY  = 2        # cap so no family dominates the unseen-variant set
NOVEL_PROMPTS_PER_FAMILY = 6       # benchmark prompts kept per held-out family
N_LOOPBACK_HOLDOUT      = 30       # ERC-repair cases held out

# Curated novel families: diverse, recognizable topologies removed ENTIRELY from
# training. Only those actually present (with ERC-valid references) are used; the
# rest are skipped with a warning. Small families chosen to limit training-signal loss.
NOVEL_FAMILY_CANDIDATES = [
    "tec_peltier_controller",
    "wien_bridge_oscillator",
    "precision_rectifier",
    "usb_c_connector_cc",
    "lora_sx1276",
    "thermocouple_max31855_spi",
    "sallen_key_low_pass",
    "hot_swap_controller",
    "can_fd_transceiver",
    "ultrasonic_distance_hcsr04",
    "wheatstone_bridge_amp",
    "voltage_multiplier_cockcroft",
]


# ── Helpers ─────────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    """Normalize a prompt for stable hashing / dedup: strip, lowercase, collapse ws."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _prompt_sha1(text: str) -> str:
    return hashlib.sha1(_norm(text).encode("utf-8")).hexdigest()


def _row_signature(messages: list) -> str:
    """Stable signature for a full conversation row (used for loopback exclusion)."""
    blob = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _load_jsonl(path: Path) -> list:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _ref_circuit(assistant_content: str):
    """Parse the assistant circuit JSON; return (circuit_dict, valid_bool) or (None, False)."""
    try:
        circ = json.loads(assistant_content)
    except Exception:
        return None, False
    try:
        res = analyze_schematic(circ.get("circuit", circ))
        return circ, bool(res["valid"])
    except Exception:
        return circ, False


def _source_fingerprint(rows: list) -> str:
    """Fingerprint the source data so we can detect drift between build and train."""
    prompts = sorted({_norm(r["messages"][1]["content"]) for r in rows})
    h = hashlib.sha1()
    h.update(str(len(rows)).encode())
    for p in prompts:
        h.update(p.encode("utf-8"))
    return h.hexdigest()


# ── Build ───────────────────────────────────────────────────────────────────

def _group_valid_refs_by_family(forward: list) -> dict[str, dict[str, dict]]:
    """family -> {prompt_sha1: item}, keeping only ERC-VALID references (clean ground
    truth), deduped by normalized prompt (first valid occurrence wins)."""
    by_family: dict[str, dict[str, dict]] = defaultdict(dict)
    n_invalid_ref = 0
    for r in forward:
        msgs = r["messages"]
        prompt = msgs[1]["content"]
        sha1 = _prompt_sha1(prompt)
        fam = r.get("_meta", {}).get("family", "?")
        circ, valid = _ref_circuit(msgs[-1]["content"])
        if not valid:
            n_invalid_ref += 1
            continue
        if sha1 not in by_family[fam]:
            by_family[fam][sha1] = {
                "prompt": prompt,
                "prompt_sha1": sha1,
                "family": fam,
                "reference_circuit": circ,
                "n_components": r.get("_meta", {}).get("n_components"),
                "difficulty": r.get("_meta", {}).get("difficulty"),
            }
    print(f"Skipped {n_invalid_ref} rows whose reference failed ERC (kept clean refs only)")
    return by_family


def _select_novel_family(rng, forward, by_family, novel_families, novel_set,
                         bench, exclude_hashes, chosen) -> int:
    """novel_family partition: exclude EVERY prompt of each novel family from training,
    sample a few per family as benchmark items. Mutates bench/exclude_hashes/chosen.
    Returns the count of benchmark items added."""
    before = len(bench)
    for fam in novel_families:
        items = list(by_family.get(fam, {}).values())
        for it in items:
            exclude_hashes.add(it["prompt_sha1"])
        rng.shuffle(items)
        added = 0
        for it in items:
            if added >= NOVEL_PROMPTS_PER_FAMILY:
                break
            if it["prompt_sha1"] in chosen:
                continue
            bench.append({**it, "partition": "novel_family"})
            chosen.add(it["prompt_sha1"])
            added += 1
    # Also exclude novel-family prompts whose reference was INVALID (not in by_family):
    # walk the raw rows so no novel-family spec leaks into training.
    for r in forward:
        if r.get("_meta", {}).get("family", "?") in novel_set:
            exclude_hashes.add(_prompt_sha1(r["messages"][1]["content"]))
    return len(bench) - before


def _select_unseen_variant(rng, by_family, novel_set, bench, exclude_hashes, chosen) -> int:
    """unseen_variant partition: from NON-novel families, pick up to
    MAX_PROMPTS_PER_FAMILY distinct prompts each, round-robin across families for
    coverage, until the target. Mutates bench/exclude_hashes/chosen; returns count added."""
    pools: dict[str, list[dict]] = {}
    for fam, items in by_family.items():
        if fam in novel_set or fam == "?":
            continue
        lst = list(items.values())
        rng.shuffle(lst)
        pools[fam] = lst

    fam_order = sorted(pools.keys())
    rng.shuffle(fam_order)
    taken_per_family: dict[str, int] = defaultdict(int)
    n_unseen = 0
    progressed = True
    while n_unseen < TARGET_UNSEEN_VARIANT and progressed:
        progressed = False
        for fam in fam_order:
            if n_unseen >= TARGET_UNSEEN_VARIANT:
                break
            if taken_per_family[fam] >= MAX_PROMPTS_PER_FAMILY:
                continue
            pool = pools[fam]
            idx = taken_per_family[fam]
            if idx < len(pool):
                it = pool[idx]
                taken_per_family[fam] += 1
                progressed = True
                if it["prompt_sha1"] in chosen:
                    continue   # already used (collision across families) - skip
                bench.append({**it, "partition": "unseen_variant"})
                exclude_hashes.add(it["prompt_sha1"])
                chosen.add(it["prompt_sha1"])
                n_unseen += 1
    return n_unseen


def _select_loopback_holdout(rng) -> tuple[list, list]:
    """Hold out N_LOOPBACK_HOLDOUT ERC-repair cases. Returns (bench_rows, exclude_sigs)."""
    loopback = _load_jsonl(LOOPBACK_SRC)
    rng.shuffle(loopback)
    lb_bench, lb_excl = [], []
    for r in loopback[:N_LOOPBACK_HOLDOUT]:
        msgs = r["messages"]
        sig = _row_signature(msgs)
        lb_excl.append(sig)
        # repair input = everything up to (but not including) the final corrected answer
        lb_bench.append({
            "signature": sig,
            "input_messages": msgs[:-1],
            "reference_fixed": msgs[-1]["content"],
        })
    return lb_bench, lb_excl


def _write_outputs(bench, exclude_hashes, lb_bench, lb_excl, manifest) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_BENCH, "w", encoding="utf-8") as fh:
        for i, b in enumerate(bench):
            fh.write(json.dumps({"id": f"hold-{i:04d}", **b}, ensure_ascii=False) + "\n")
    with open(OUT_EXCLUDE, "w", encoding="utf-8") as fh:
        for h in sorted(exclude_hashes):
            fh.write(h + "\n")
    with open(OUT_LB_BENCH, "w", encoding="utf-8") as fh:
        for b in lb_bench:
            fh.write(json.dumps(b, ensure_ascii=False) + "\n")
    with open(OUT_LB_EXCL, "w", encoding="utf-8") as fh:
        for s in sorted(lb_excl):
            fh.write(s + "\n")
    with open(OUT_MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)


def build():
    rng = random.Random(SEED)

    forward = _load_jsonl(FORWARD_SRC)
    print(f"Loaded {len(forward)} forward rows from {FORWARD_SRC.name}")
    src_fp = _source_fingerprint(forward)

    present_families = {r.get("_meta", {}).get("family", "?") for r in forward}
    novel_families = [f for f in NOVEL_FAMILY_CANDIDATES if f in present_families]
    missing = [f for f in NOVEL_FAMILY_CANDIDATES if f not in present_families]
    if missing:
        print(f"[warn] novel-family candidates not in data (skipped): {missing}")
    novel_set = set(novel_families)
    print(f"Novel families held out entirely: {len(novel_families)} -> {novel_families}")

    by_family = _group_valid_refs_by_family(forward)

    bench: list[dict] = []
    exclude_hashes: set[str] = set()
    chosen: set[str] = set()   # global dedup - a prompt can occur under >1 family

    n_novel = _select_novel_family(rng, forward, by_family, novel_families, novel_set,
                                   bench, exclude_hashes, chosen)
    print(f"novel_family benchmark prompts: {n_novel}")

    n_unseen = _select_unseen_variant(rng, by_family, novel_set, bench, exclude_hashes, chosen)
    print(f"unseen_variant benchmark prompts: {n_unseen} "
          f"(from {len({b['family'] for b in bench if b['partition']=='unseen_variant'})} families)")

    lb_bench, lb_excl = _select_loopback_holdout(rng)
    print(f"loopback repair holdout: {len(lb_bench)} cases")

    manifest = {
        "version": "v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "source_file": FORWARD_SRC.name,
        "source_fingerprint": src_fp,
        "source_row_count": len(forward),
        "novel_families": novel_families,
        "counts": {
            "benchmark_total": len(bench),
            "novel_family": n_novel,
            "unseen_variant": n_unseen,
            "excluded_prompt_hashes": len(exclude_hashes),
            "loopback_holdout": len(lb_bench),
        },
        "all_references_pass_erc": True,  # enforced above (only valid refs kept)
    }
    _write_outputs(bench, exclude_hashes, lb_bench, lb_excl, manifest)

    print("\nWrote:")
    for p in (OUT_BENCH, OUT_EXCLUDE, OUT_LB_BENCH, OUT_LB_EXCL, OUT_MANIFEST):
        print(f"  {p.relative_to(ROOT)}")
    print(f"\nTotal benchmark prompts: {len(bench)}  "
          f"(novel_family={n_novel}, unseen_variant={n_unseen})")
    print(f"Prompt hashes excluded from training: {len(exclude_hashes)}")
    verify()


# ── Verify ──────────────────────────────────────────────────────────────────

def verify():
    """Re-load the frozen set and assert (a) every reference passes ERC and (b) every
    benchmark prompt's hash is in the exclude file (so it cannot leak into training)."""
    print("\n--- verify ---")
    bench = _load_jsonl(OUT_BENCH)
    excl = {l.strip() for l in OUT_EXCLUDE.read_text().splitlines() if l.strip()}

    bad_ref = 0
    not_excluded = 0
    for b in bench:
        circ = b["reference_circuit"]
        res = analyze_schematic(circ.get("circuit", circ))
        if not res["valid"]:
            bad_ref += 1
        if b["prompt_sha1"] not in excl:
            not_excluded += 1

    print(f"benchmark items: {len(bench)}")
    print(f"references failing ERC: {bad_ref}  (must be 0)")
    print(f"benchmark prompts NOT in exclude set: {not_excluded}  (must be 0)")

    # cross-check: no benchmark prompt collides across partitions
    seen = {}
    dupes = 0
    for b in bench:
        if b["prompt_sha1"] in seen:
            dupes += 1
        seen[b["prompt_sha1"]] = b["partition"]
    print(f"duplicate prompts across benchmark: {dupes}  (must be 0)")

    ok = (bad_ref == 0 and not_excluded == 0 and dupes == 0)
    print("VERIFY:", "PASS" if ok else "FAIL")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-only", action="store_true",
                    help="Only re-verify an existing frozen benchmark.")
    args = ap.parse_args()
    if args.verify_only:
        verify()
    else:
        build()
