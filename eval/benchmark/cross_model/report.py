"""Stage 3 - REPORT (deterministic tables from verified/).

    python -m eval.benchmark.cross_model.report [--suite forward]

Per (model, suite): N, delivered-clean rate + Wilson 95% CI, blocked/broken rate,
availability, mean latency, cost, plus per-category breakdown. Headline columns:
  precision     of what REACHED THE USER, % ERC-clean (killswitch pushes Ohmatic
                to ~100; hosted deliver everything, so precision == raw pass rate)
  availability  % of requests that got a circuit (the price the killswitch pays)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval.benchmark.cross_model import config as C


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="", help="filter to one suite")
    ap.add_argument("--by-category", action="store_true")
    args = ap.parse_args()

    rows = []
    for path in sorted(C.VERIFIED_DIR.glob("*.jsonl")):
        rows += [json.loads(l) for l in path.read_text(encoding="utf-8")
                 .splitlines() if l.strip()]
    if args.suite:
        rows = [r for r in rows if r["suite"] == args.suite]
    if not rows:
        raise SystemExit("No verified rows - run verify.py first.")

    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        groups[(r["model"], r["suite"])].append(r)

    hdr = (f"{'model':14s} {'suite':10s} {'N':>4s} {'clean%':>7s} "
           f"{'95% CI':>13s} {'blocked%':>8s} {'broken%':>8s} {'avail%':>7s} "
           f"{'prec%':>6s} {'lat_s':>6s} {'cost$':>7s}")
    print(hdr)
    print("-" * len(hdr))
    for (model, suite), g in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        n = len(g)
        clean   = sum(r["outcome"] == "delivered_clean"    for r in g)
        blocked = sum(r["outcome"] == "blocked_killswitch" for r in g)
        broken  = sum(r["outcome"] in ("delivered_broken", "invalid_output") for r in g)
        delivered = clean + sum(r["outcome"] == "delivered_broken" for r in g)
        lo, hi  = wilson(clean, n)
        avail   = (n - blocked) / n
        prec    = clean / delivered if delivered else 0.0
        lat     = sum(r.get("latency_s") or 0 for r in g) / n
        cost    = sum(r.get("cost_usd") or 0 for r in g)
        print(f"{model:14s} {suite:10s} {n:4d} {clean/n:7.1%} "
              f"[{lo:5.1%},{hi:5.1%}] {blocked/n:8.1%} {broken/n:8.1%} "
              f"{avail:7.1%} {prec:6.1%} {lat:6.1f} {cost:7.2f}")

    if args.by_category:
        print("\nPer-category delivered-clean rate:")
        cats: dict[tuple, list] = defaultdict(list)
        for r in rows:
            cats[(r["model"], r["suite"], r.get("category", "?"))].append(r)
        for (model, suite, cat), g in sorted(cats.items()):
            k = sum(r["outcome"] == "delivered_clean" for r in g)
            print(f"  {model:14s} {suite:10s} {cat:28s} {k:3d}/{len(g):<3d} {k/len(g):6.1%}")


if __name__ == "__main__":
    main()
