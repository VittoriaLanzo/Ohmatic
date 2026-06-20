"""Regenerate assets/benchmark.png from the cross-model results.

Horizontal stacked bars: green = delivered & passes ERC, gold = killswitch refusal
(safe), red = broken circuit delivered. Wilson 95% CI whisker on the clean rate.

    python -m eval.benchmark.cross_model.plot_benchmark

Numbers are the ERC-clean counts per leg (full 75-prompt realuser suite):
  bf16 70/75   Fable5 57/75 (xhigh)   Opus 57/75 (max)   Codex 56/75 (xhigh)   Q4_K_M 54/75   base 3/75.
Effort scales differ - Claude is low<medium<high<xhigh<max, Codex tops out at xhigh - so
Opus ran at Claude's max, Codex at its own max (xhigh), and Fable at xhigh (one below
Claude's max). Opus also authored the prompts (home-field). Per-leg effort table in the README.
"""
from __future__ import annotations
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

BG = "#0d1117"; GREEN = "#3fb950"; GOLD = "#bb8009"; RED = "#f85149"
FG = "#e6edf3"; MUTED = "#8b949e"; GRID = "#30363d"

# label, clean, total, rest_kind
MODELS = [
    ("Ohmatic bf16\nfull pipeline · 8B",          70, 75, "blocked"),
    ("Claude Fable 5\nfrontier · xhigh effort",   57, 75, "broken"),
    ("Claude Opus 4.8\nfrontier · max effort *",  57, 75, "broken"),
    ("OpenAI Codex\nfrontier · xhigh effort",     56, 75, "broken"),
    ("Ohmatic Q4_K_M\nGGUF quant",                54, 75, "blocked"),
    ("Qwen3-8B base\nuntrained · single-shot",     3, 75, "broken"),
]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h) * 100, (c + h) * 100


fig, ax = plt.subplots(figsize=(14.2, 9.3), dpi=200)
fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
ys = list(range(len(MODELS)))[::-1]   # first model on top

for y, (label, clean, total, kind) in zip(ys, MODELS):
    pct = 100 * clean / total
    rest = 100 - pct
    rest_color = RED if kind == "broken" else GOLD
    ax.barh(y, pct, color=GREEN, height=0.62, zorder=2)
    ax.barh(y, rest, left=pct, color=rest_color, height=0.62, zorder=2)
    lo, hi = wilson(clean, total)
    if pct >= 25:
        ax.text(pct / 2, y, f"{pct:.1f}% ERC-clean", ha="center", va="center",
                color="#0d1117" if pct > 40 else FG, fontsize=15, fontweight="bold", zorder=6)
    else:                                  # green sliver too small for the label - place it past the CI whisker
        ax.text(hi + 2.5, y, f"{pct:.1f}% ERC-clean", ha="left", va="center",
                color="#ffffff", fontsize=13.5, fontweight="bold", zorder=6)
    rest_label_color = "#ffffff" if kind == "broken" else "#0d1117"
    if rest >= 14:                         # wide enough for the descriptive two-line label
        msg = f"{rest:.0f}% BROKEN\ndelivered to user" if kind == "broken" else f"{rest:.0f}%\nblocked"
        ax.text(pct + rest / 2, y, msg, ha="center", va="center",
                color=rest_label_color, fontsize=11.5, fontweight="bold", zorder=4)
    else:                                  # narrow sliver - keep it to the percent only
        ax.text(pct + rest / 2, y, f"{rest:.0f}%", ha="center", va="center",
                color=rest_label_color, fontsize=11, fontweight="bold", zorder=4)
    ax.text(101.5, y, f"n={total}", ha="left", va="center", color=MUTED, fontsize=12)
    ax.errorbar(pct, y, xerr=[[pct - lo], [hi - pct]], fmt="none", ecolor="#ffffff",
                elinewidth=2, capsize=6, capthick=2, zorder=5)

ax.set_yticks(ys)
ax.set_yticklabels([m[0] for m in MODELS], color=FG, fontsize=12.5)
ax.set_xlim(0, 100); ax.set_xticks([0, 25, 50, 75, 100])
ax.tick_params(colors=MUTED, labelsize=11)
for s in ax.spines.values():
    s.set_visible(False)
ax.xaxis.grid(True, color=GRID, linewidth=1, zorder=0)
ax.set_axisbelow(True)
ax.set_title("If it can't verify it, it won't deliver it.", color=FG, fontsize=22,
             fontweight="bold", loc="left", pad=34)
ax.text(0, 1.045, "75 novel real-user prompts · identical prompts and ERC verifier for "
        "every model · paired McNemar Ohmatic-vs-Fable p = 0.007",
        transform=ax.transAxes, color=MUTED, fontsize=12.5)
legend = [Patch(facecolor=GREEN, label="delivered · passes ERC"),
          Patch(facecolor=GOLD, label="killswitch refusal (asks to clarify)"),
          Patch(facecolor=RED, label="broken circuit delivered")]
ax.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3,
          frameon=False, labelcolor=FG, fontsize=12, handlelength=1.3)

fig.text(0.16, 0.04,
         "*  Opus authored the 75 prompts - a home-field advantage biasing in Opus's favour. Effort: Opus at Claude's max,\n"
         "   Fable & Codex at xhigh (Codex's ceiling). Every competitor also gets Ohmatic's full spec, which overstates a bare model.",
         color=MUTED, fontsize=11, ha="left", va="bottom")

out = Path(__file__).resolve().parents[3] / "assets" / "benchmark.png"
fig.subplots_adjust(left=0.16, right=0.93, top=0.82, bottom=0.205)
fig.savefig(out, facecolor=BG, dpi=200)
print("wrote", out)
