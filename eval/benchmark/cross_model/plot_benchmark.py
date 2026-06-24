"""Regenerate assets/benchmark.svg from the verified PCBBench results.

A solder-pad matrix in the Ohmatic PCB-board visual language. Every one of the 62
PCBBench tasks is a single pad, one row per leg, sorted by outcome: phosphor-green
(delivered & passes ERC), amber (killswitch abstention), LED-red (a broken circuit
delivered to the user). The contrast reads like a board at a glance - the Ohmatic
legs show green and amber pads and zero red; a frontier model that always answers
shows red. Abstained vs broken, made literal.

    python -m eval.benchmark.cross_model.plot_benchmark

Data-driven and expansible: each leg is read from verified/<leg>.jsonl
(suite=pcbschemagen); a leg with no file is skipped, so bf16 - and any future leg -
drops in as a new row automatically. No matplotlib: pure SVG, crisp at any size in
the README and on the site, numbers never hard-coded (rerun verify.py to update).
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERIFIED = HERE / "verified"
SUITE = "pcbschemagen"

BOARD   = "#081712"
PANEL   = "#0b201a"
COPPER  = "#c47a3d"
COPPERB = "#f59e4d"
GOLD    = "#ffd072"
SILK    = "#e9f2e7"
SILKDIM = "#9db3a4"
GREEN   = "#51e88a"   # delivered & passes ERC
AMBER   = "#ffb145"   # abstained / killswitch
RED     = "#ff5c49"   # broken circuit delivered
LINE    = "rgba(196,122,61,0.20)"
LINESTR = "rgba(196,122,61,0.42)"
FONT    = "'Fragment Mono','Cascadia Code',ui-monospace,'DejaVu Sans Mono','Courier New',monospace"

LEGS = [
    ("q4",    "Ohmatic Q4_K_M", "GGUF quant · 8B",       "ohmatic"),
    ("q8",    "Ohmatic Q8_0",   "GGUF quant · 8B",       "ohmatic"),
    ("bf16",  "Ohmatic bf16",   "full precision · 8B",   "ohmatic"),
    ("codex", "OpenAI Codex",   "frontier · xhigh effort", "frontier"),
]


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
    blocked = sum(r["outcome"] == "blocked_killswitch" for r in rows)
    broken = sum(r["outcome"] in ("delivered_broken", "invalid_output") for r in rows)
    return dict(n=n, clean=clean, blocked=blocked, broken=broken)


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def txt(x, y, s, size, fill, weight=400, anchor="start", ls=0.0, op=1.0):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    l = f' letter-spacing="{ls}"' if ls else ""
    o = f' opacity="{op}"' if op != 1.0 else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}"{a}{l}{o}>{esc(s)}</text>')


legs = [(lab, sub, kind, load_leg(k)) for k, lab, sub, kind in LEGS]
legs = [(lab, sub, kind, d) for lab, sub, kind, d in legs if d]

# ---- geometry ----------------------------------------------------------------
W = 1180
PAD = 34
GUTTER_R = 252               # leg-label column ends here
STRIP_X0 = 270
STRIP_X1 = W - 150           # leaves a column for the per-leg counts
NCOLS = max((d["n"] for *_, d in legs), default=62)
PITCH = (STRIP_X1 - STRIP_X0) / NCOLS
DOT = min(14.5, PITCH - 1.8)
HEAD = 142
ROW = 60
FOOT = 118
H = HEAD + ROW * len(legs) + FOOT

s = []
s.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'width="{W}" height="{H}" font-family="{FONT}" role="img">')
s.append('<defs><pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
         f'<circle cx="1.1" cy="1.1" r="1.1" fill="{COPPER}" opacity="0.06"/></pattern></defs>')
s.append(f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="14" fill="{BOARD}" '
         f'stroke="{LINESTR}" stroke-width="1.5"/>')
s.append(f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="14" fill="url(#dots)"/>')
for cx, cy in [(PAD, PAD), (W-PAD, PAD), (PAD, H-PAD), (W-PAD, H-PAD)]:
    s.append(f'<circle cx="{cx}" cy="{cy}" r="5.5" fill="none" stroke="{COPPER}" '
             f'stroke-width="1.2" opacity="0.5"/><circle cx="{cx}" cy="{cy}" r="1.6" fill="{COPPER}" opacity="0.5"/>')

# ---- header ------------------------------------------------------------------
s.append(txt(PAD + 10, 56, "If it can't verify it, it won't deliver it.", 27, SILK, 700))
s.append(txt(PAD + 10, 86, "62 PCBBench tasks (PCBSchemaGen, MIT)  ·  one ERC verifier for every leg  ·  condition C1  ·  each pad = one task",
             13, SILKDIM, 400))
s.append(txt(STRIP_X1 + 24, 86, "outcome", 11, SILKDIM, 400, op=0.7))

# ---- rows --------------------------------------------------------------------
for i, (lab, sub, kind, d) in enumerate(legs):
    rtop = HEAD + i * ROW
    mid = rtop + ROW / 2
    if i > 0 and kind != legs[i-1][2]:                       # divider: ours vs frontier
        s.append(f'<line x1="{PAD+10}" y1="{rtop:.1f}" x2="{W-PAD-10}" y2="{rtop:.1f}" '
                 f'stroke="{LINE}" stroke-width="1" stroke-dasharray="2 4"/>')
    s.append(f'<rect x="{PAD+6}" y="{rtop+8:.1f}" width="{W-2*PAD-12}" height="{ROW-16:.1f}" '
             f'rx="9" fill="{PANEL}" opacity="0.5"/>')
    s.append(txt(GUTTER_R, mid - 3, lab, 15.5, SILK, 700, anchor="end"))
    s.append(txt(GUTTER_R, mid + 14, sub, 10.5, SILKDIM, 400, anchor="end"))

    pads = [GREEN] * d["clean"] + [AMBER] * d["blocked"] + [RED] * d["broken"]
    py = mid - DOT / 2
    for idx, col in enumerate(pads):
        px = STRIP_X0 + idx * PITCH + (PITCH - DOT) / 2
        s.append(f'<rect x="{px:.1f}" y="{py:.1f}" width="{DOT:.1f}" height="{DOT:.1f}" '
                 f'rx="{DOT*0.3:.1f}" fill="{col}" stroke="rgba(0,0,0,0.25)" stroke-width="0.5"/>')

    # per-leg counts (colored), right-aligned; broken emphasized
    bw = 700 if d["broken"] else 400
    s.append(f'<text x="{W-PAD-10:.1f}" y="{mid+5:.1f}" font-family="{FONT}" font-size="12.5" '
             f'text-anchor="end">'
             f'<tspan fill="{GREEN}" font-weight="700">{d["clean"]}</tspan>'
             f'<tspan fill="{SILKDIM}"> · </tspan>'
             f'<tspan fill="{AMBER}" font-weight="700">{d["blocked"]}</tspan>'
             f'<tspan fill="{SILKDIM}"> · </tspan>'
             f'<tspan fill="{RED}" font-weight="{bw}">{d["broken"]}</tspan></text>')

# ---- legend + footnote -------------------------------------------------------
ly = H - FOOT + 36
lx = PAD + 12
for col, label in [(GREEN, "verified-clean"), (AMBER, "abstained · killswitch"), (RED, "broken delivered")]:
    s.append(f'<rect x="{lx}" y="{ly-11:.1f}" width="15" height="15" rx="4.5" fill="{col}"/>')
    s.append(txt(lx + 22, ly + 1, label, 12, SILK, 400))
    lx += 22 + len(label) * 7.5 + 30
s.append(txt(W - PAD - 10, ly + 1, "counts:  clean · abstained · broken", 11, SILKDIM, 400, anchor="end", op=0.85))
s.append(txt(PAD + 12, ly + 31,
             "Same prompts and the same deterministic ERC verifier for every leg; competitors get the schema + registry but not the ERC rules (condition C1).",
             11, SILKDIM, 400, op=0.9))
s.append(txt(PAD + 12, ly + 49,
             "Scope caveat: Ohmatic is trained to ≤30-component circuits; PCBBench spans up to 50 — its largest tasks are out-of-scope and fall among its abstentions.",
             11, AMBER, 400, op=0.85))
s.append('</svg>')

out = HERE.parents[2] / "assets" / "benchmark.svg"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(s), encoding="utf-8")
print("wrote", out, "->", ", ".join(f"{lab} {d['clean']}/{d['blocked']}/{d['broken']}" for lab, _, _, d in legs))
