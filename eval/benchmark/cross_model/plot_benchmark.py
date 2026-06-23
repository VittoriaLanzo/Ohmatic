"""Regenerate assets/benchmark.png from the verified PCBBench results.

Diverging horizontal bars around a central "delivery line" (x=0). The only UNSAFE
outcome - a broken circuit handed to the user - is drawn in red to the LEFT of the
line; the two safe outcomes - a verified-clean circuit (green) and a killswitch
abstention (gold) - extend RIGHT. So an Ohmatic leg, which abstains rather than ship
an ERC-failing circuit, never crosses into the danger zone; a frontier model that
always answers does. That contrast - blocked-and-delivered vs abstained - is the point.

    python -m eval.benchmark.cross_model.plot_benchmark

Data-driven: each leg is read from verified/<leg>.jsonl (suite=pcbschemagen). A leg
with no verified file is skipped, so bf16 appears automatically once its run lands.
Numbers are never hard-coded here - rerun verify.py and this picks them up.
"""
from __future__ import annotations
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

HERE = Path(__file__).resolve().parent
VERIFIED = HERE / "verified"
SUITE = "pcbschemagen"

BG = "#0d1117"; GREEN = "#3fb950"; GOLD = "#bb8009"; RED = "#f85149"
FG = "#e6edf3"; MUTED = "#8b949e"; GRID = "#30363d"

# leg key -> display label. Order top->bottom; missing legs are skipped silently
# (bf16 slots in here automatically once verified/bf16.jsonl exists).
LEGS = [
    ("q4",    "Ohmatic Q4_K_M\nGGUF quant · 8B"),
    ("q8",    "Ohmatic Q8_0\nGGUF quant · 8B"),
    ("bf16",  "Ohmatic bf16\nfull precision · 8B"),
    ("codex", "OpenAI Codex\nfrontier · xhigh effort"),
]


def wilson_hi(k: int, n: int, z: float = 1.96) -> float:
    """Upper 95% bound on the broken rate; for k=0 this is the rule-of-three read."""
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c + h) * 100


def load_leg(key: str) -> dict | None:
    f = VERIFIED / f"{key}.jsonl"
    if not f.exists():
        return None
    rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r.get("suite") == SUITE]
    if not rows:
        return None
    n = len(rows)
    clean = sum(r["outcome"] == "delivered_clean" for r in rows)
    broken = sum(r["outcome"] == "delivered_broken" for r in rows)
    blocked = sum(r["outcome"] == "blocked_killswitch" for r in rows)
    invalid = sum(r["outcome"] == "invalid_output" for r in rows)
    return dict(n=n, clean=clean, broken=broken + invalid, blocked=blocked,
                clean_pct=100 * clean / n, broken_pct=100 * (broken + invalid) / n,
                blocked_pct=100 * blocked / n)


legs = [(label, load_leg(key)) for key, label in LEGS]
legs = [(label, d) for label, d in legs if d]   # drop legs with no data yet

fig, ax = plt.subplots(figsize=(14.4, 0.2 + 1.9 * len(legs)), dpi=200)
fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
ys = list(range(len(legs)))[::-1]               # first leg on top
H = 0.6

left_max = max((d["broken_pct"] for _, d in legs), default=0)
XL = -(math.ceil((left_max + 6) / 10) * 10)     # round the danger axis out to a clean tick

for y, (label, d) in zip(ys, legs):
    # RIGHT of the delivery line: the two SAFE outcomes
    ax.barh(y, d["clean_pct"], left=0, color=GREEN, height=H, zorder=3)
    ax.barh(y, d["blocked_pct"], left=d["clean_pct"], color=GOLD, height=H, zorder=3)
    # LEFT of the delivery line: the one UNSAFE outcome
    ax.barh(y, -d["broken_pct"], left=0, color=RED, height=H, zorder=3)

    if d["clean_pct"] >= 12:
        ax.text(d["clean_pct"] / 2, y, f"{d['clean']}/{d['n']}\nclean", ha="center",
                va="center", color="#0d1117", fontsize=12, fontweight="bold", zorder=6)
    if d["blocked_pct"] >= 12:
        ax.text(d["clean_pct"] + d["blocked_pct"] / 2, y, f"{d['blocked']}\nabstained",
                ha="center", va="center", color="#0d1117", fontsize=12,
                fontweight="bold", zorder=6)
    if d["broken"] > 0:
        ax.text(-d["broken_pct"] - 1.5, y, f"{d['broken']} BROKEN\ndelivered", ha="right",
                va="center", color=RED, fontsize=12.5, fontweight="bold", zorder=6)
    else:                                        # 0 broken: rule-of-three 95% upper bound (3/n)
        ax.text(-1.5, y, f"0 broken  (≤{300 / d['n']:.1f}% @95%)", ha="right",
                va="center", color=GREEN, fontsize=11.5, fontweight="bold", zorder=6)
    ax.text(101.5, y, f"n={d['n']}", ha="left", va="center", color=MUTED, fontsize=11.5)

# the delivery line: everything left of it reached the user broken
ax.axvline(0, color="#ffffff", linewidth=1.8, zorder=5)

ax.set_yticks(ys)
ax.set_yticklabels([label for label, _ in legs], color=FG, fontsize=12.5)
ax.set_xlim(XL, 104)
ticks = list(range(XL, 101, 20))
ax.set_xticks(ticks)
ax.set_xticklabels([f"{abs(t)}%" for t in ticks], color=MUTED, fontsize=11)
ax.tick_params(colors=MUTED)
for s in ax.spines.values():
    s.set_visible(False)
ax.xaxis.grid(True, color=GRID, linewidth=1, zorder=0)
ax.set_axisbelow(True)

# region headers above the bars: danger (left) vs safe (right)
top = len(legs) - 0.5
ax.text(XL / 2, top + 0.25, "◀  BROKEN circuit delivered  (unsafe)", ha="center",
        va="bottom", color=RED, fontsize=12, fontweight="bold")
ax.text(50, top + 0.25, "verified-clean  +  abstained  (no broken circuit shipped)  ▶",
        ha="center", va="bottom", color=GREEN, fontsize=12, fontweight="bold")

ax.set_title("If it can't verify it, it won't deliver it.", color=FG, fontsize=22,
             fontweight="bold", loc="left", pad=46)
ax.text(0, 1.0, "62 PCBBench tasks (PCBSchemaGen, MIT) · same prompts + same ERC verifier "
        "every leg · condition C1", transform=ax.transAxes, color=MUTED, fontsize=12, va="bottom")

legend = [Patch(facecolor=GREEN, label="delivered · passes ERC"),
          Patch(facecolor=GOLD, label="abstained · killswitch (asks to clarify)"),
          Patch(facecolor=RED, label="broken circuit delivered to user")]
ax.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.5, -0.16 / max(1, len(legs)) - 0.06),
          ncol=3, frameon=False, labelcolor=FG, fontsize=11.5, handlelength=1.3)

out = HERE.parents[2] / "assets" / "benchmark.png"
out.parent.mkdir(parents=True, exist_ok=True)
fig.subplots_adjust(left=0.16, right=0.94, top=0.80, bottom=0.16)
fig.savefig(out, facecolor=BG, dpi=200)
print("wrote", out, "->", ", ".join(f"{lab.splitlines()[0]} {d['clean']}/{d['n']}c "
                                    f"{d['blocked']}a {d['broken']}b" for lab, d in legs))
