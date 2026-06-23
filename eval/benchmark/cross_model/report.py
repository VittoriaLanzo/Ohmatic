"""Stage 3 - REPORT (deterministic, audit-grade tables from verified/).

    python -m eval.benchmark.cross_model.report [--suite forward] [--by-category]

Axes are kept SEPARATE (an auditor should never see JSON-format failures folded into
"broken"):
  json%        valid parseable+schema JSON (outcome != invalid_output) -- the format gate
  erc-clean%   delivered AND zero ERC diagnostics (+ Wilson 95% CI)
  graded       partial-credit ERC in [0,1] (severity-weighted; 1.0 = clean) -- not a bit
  broken%      delivered a circuit that FAILS ERC (valid JSON, bad circuit) [rule-of-3 if 0]
  invalid%     emitted no valid JSON (format failure, distinct from a broken circuit)
  blocked%     killswitch refusal (the price of the never-ship-broken guarantee)
  avail%       coverage = % of requests that got a delivered circuit
  prec%        of what was delivered, % ERC-clean
  AUGRC        Area Under Generalized Risk-Coverage (Traub et al., NeurIPS 2024) = the
               average risk of UNDETECTED failures; lower is better. The metric the
               killswitch is built to minimise. Nobody else in this space reports it.
Plus per-model error-code histograms and paired McNemar (model-vs-model, by prompt_id).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval.benchmark.cross_model import config as C

# --- severity grading (single-sourced from the ERC taxonomy) ---
_TAX = json.loads((_ROOT / "eval" / "error_taxonomy.json").read_text(encoding="utf-8")).get("codes", {})
def _severity(code: str) -> str:
    e = _TAX.get(code)
    return (e.get("severity") if isinstance(e, dict) else None) or "error"

def _err_warn(diag_codes) -> tuple[int, int]:
    errs = sum(1 for c in (diag_codes or []) if _severity(c) == "error")
    warns = sum(1 for c in (diag_codes or []) if _severity(c) == "warning")
    return errs, warns

def _graded(diag_codes) -> float:
    """Partial-credit ERC in [0,1]: 1.0 clean; an error costs 0.34, a warning 0.10 (capped)."""
    e, w = _err_warn(diag_codes)
    return max(0.0, 1.0 - (0.34 * e + 0.10 * w))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def augrc(items: list[tuple[float, bool]]) -> tuple[float, list[tuple[float, float]]]:
    """items = (confidence, is_failure). Rank by confidence (deliver high-conf first); at each
    coverage the GENERALIZED risk = cumulative failures / N (share of all, not of covered).
    AUGRC = mean generalized-risk over coverage. Lower is better."""
    s = sorted(items, key=lambda x: x[0], reverse=True)
    n = len(s)
    if n == 0:
        return 0.0, []
    cum, area, curve = 0, 0.0, []
    for i, (_conf, fail) in enumerate(s, 1):
        cum += int(fail)
        gr = cum / n
        curve.append((i / n, gr))
        area += gr / n
    return area, curve


def mcnemar(b: int, c: int) -> tuple[float, float]:
    """b = A-clean & B-broken; c = A-broken & B-clean. Continuity-corrected chi2 + p (1 df)."""
    nd = b + c
    if nd == 0:
        return 0.0, 1.0
    chi2 = (abs(b - c) - 1) ** 2 / nd
    return chi2, math.erfc(math.sqrt(chi2 / 2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="", help="filter to one suite")
    ap.add_argument("--by-category", action="store_true")
    args = ap.parse_args()

    rows = []
    for path in sorted(C.VERIFIED_DIR.glob("*.jsonl")):
        rows += [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.suite:
        rows = [r for r in rows if r["suite"] == args.suite]
    if not rows:
        raise SystemExit("No verified rows - run verify.py first.")

    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        groups[(r["model"], r["suite"])].append(r)

    # ---- main table: axes kept separate ----
    hdr = (f"{'model':14s} {'suite':10s} {'N':>4s} {'json%':>6s} {'erc-cln%':>8s} "
           f"{'95% CI':>13s} {'graded':>6s} {'broken%':>8s} {'inval%':>6s} "
           f"{'block%':>6s} {'avail%':>6s} {'prec%':>6s} {'AUGRC':>6s}")
    print(hdr); print("-" * len(hdr))
    notes = []
    for (model, suite), g in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        n = len(g)
        invalid = sum(r["outcome"] == "invalid_output" for r in g)
        clean   = sum(r["outcome"] == "delivered_clean" for r in g)
        broken  = sum(r["outcome"] == "delivered_broken" for r in g)
        blocked = sum(r["outcome"] == "blocked_killswitch" for r in g)
        valid   = n - invalid
        delivered = clean + broken
        lo, hi  = wilson(clean, n)
        graded  = sum(_graded(r.get("diag_codes")) for r in g) / n
        avail   = delivered / n
        prec    = clean / delivered if delivered else 0.0
        au, _   = augrc([( -(r.get("n_diags") or 0), (r.get("n_diags") or 0) > 0) for r in g])
        bk_str  = f"{broken/n:7.1%}"
        if broken == 0:
            bk_str = f"  0(≤{3/n:.1%})"; notes.append(f"{model}/{suite}: 0 broken in {n} → 95% upper bound ≤ {3/n:.2%} (rule of 3)")
        print(f"{model:14s} {suite:10s} {n:4d} {valid/n:6.1%} {clean/n:8.1%} "
              f"[{lo:4.0%},{hi:4.0%}] {graded:6.2f} {bk_str:>8s} {invalid/n:6.1%} "
              f"{blocked/n:6.1%} {avail:6.1%} {prec:6.1%} {au:6.3f}")
    for nt in notes:
        print("  · " + nt)

    # ---- per-model error-code histogram (which ERC rules each model trips) ----
    print("\nTop failing ERC codes per model (severity in brackets):")
    for (model, suite), g in sorted(groups.items()):
        hist = Counter(c for r in g for c in (r.get("diag_codes") or []))
        if not hist:
            continue
        top = ", ".join(f"{c}[{_severity(c)[0]}]×{k}" for c, k in hist.most_common(5))
        print(f"  {model:14s} {suite:10s} {top}")

    # ---- paired McNemar (model vs model on the ERC-clean outcome, by prompt_id) ----
    by_suite: dict[str, dict[str, dict[str, bool]]] = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        by_suite[r["suite"]][r["model"]][r["prompt_id"]] = (r["outcome"] == "delivered_clean")
    print("\nPaired McNemar on erc-clean (a-wins / b-wins / chi2 / p; apply Benjamini-Hochberg across the family):")
    for suite, mm in sorted(by_suite.items()):
        for a, b in combinations(sorted(mm), 2):
            ids = set(mm[a]) & set(mm[b])
            b_wins = sum(mm[a][i] and not mm[b][i] for i in ids)   # a clean, b not
            c_wins = sum(mm[b][i] and not mm[a][i] for i in ids)   # b clean, a not
            chi2, p = mcnemar(b_wins, c_wins)
            print(f"  {suite:10s} {a:12s} vs {b:12s}  {b_wins:3d}/{c_wins:<3d}  chi2={chi2:6.2f}  p={p:.4f}")

    if args.by_category:
        print("\nPer-category erc-clean rate:")
        cats: dict[tuple, list] = defaultdict(list)
        for r in rows:
            cats[(r["model"], r["suite"], r.get("category", "?"))].append(r)
        for (model, suite, cat), g in sorted(cats.items()):
            k = sum(r["outcome"] == "delivered_clean" for r in g)
            print(f"  {model:14s} {suite:10s} {cat:28s} {k:3d}/{len(g):<3d} {k/len(g):6.1%}")


if __name__ == "__main__":
    main()
