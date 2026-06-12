"""
grokking_signature.py - Detect & quantify the grokking transition
==================================================================
Grokking, operationally, is: TRAIN LOSS plateaus, yet held-out generalization
(here ERC pass-rate) keeps RISING after that plateau. That divergence is the
evidence the model learned the rules rather than memorizing examples - and it is
the single most defensible chart for a technical audience.

This script reads the training run's logged history (train loss + ERC pass-rate),
finds the loss-plateau step, and measures how much ERC pass-rate improved AFTER it.

Inputs (pick one):
  --run ENTITY/PROJECT/RUN_ID   read history via the wandb API (default source)
  --csv PATH                    a CSV with columns: step, train_loss, erc_pass_rate

Outputs (eval/benchmark/reports/):
  grokking_<ts>.json    the measured transition
  grokking_<ts>.md      human-readable summary
  grokking_<ts>.csv     step, train_loss, erc_pass_rate (for charting)
  grokking_<ts>.png     loss-vs-ERC chart (if matplotlib is available)

Usage:
    python eval/benchmark/grokking_signature.py --run VittoriaLanzo/ohmatic-qwen3/<run_id>
    python eval/benchmark/grokking_signature.py --csv history.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "eval" / "benchmark" / "reports"

# Column-name candidates as logged by the training script / HF WandbCallback.
LOSS_KEYS = ["train/loss", "loss", "train_loss"]
ERC_KEYS  = ["erc/pass_rate", "erc_pass_rate", "erc/best_pass_rate"]
STEP_KEYS = ["train/global_step", "global_step", "_step", "step"]

# Loss is considered "plateaued" once the smoothed loss falls within this fraction of
# its total descent from start to best. 0.10 -> within 10% of the way to its minimum.
PLATEAU_TOL = 0.10
# An ERC rise after the plateau bigger than this counts as a grokking signature.
GROK_MIN_RISE = 0.05


def _first(d: dict, keys: list):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _from_wandb(run_path: str) -> list[dict]:
    try:
        import wandb
    except ImportError:
        sys.exit("wandb not installed - `pip install wandb` or use --csv.")
    api = wandb.Api()
    run = api.run(run_path)
    rows = []
    # scan_history streams all logged points without the default 500-row sampling.
    for h in run.scan_history():
        step = _first(h, STEP_KEYS)
        loss = _first(h, LOSS_KEYS)
        erc  = _first(h, ERC_KEYS)
        if step is None:
            continue
        rows.append({"step": float(step),
                     "train_loss": None if loss is None else float(loss),
                     "erc_pass_rate": None if erc is None else float(erc)})
    return rows


def _from_csv(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                rows.append({
                    "step": float(r.get("step") or r.get("global_step")),
                    "train_loss": float(r["train_loss"]) if r.get("train_loss") not in (None, "") else None,
                    "erc_pass_rate": float(r["erc_pass_rate"]) if r.get("erc_pass_rate") not in (None, "") else None,
                })
            except (TypeError, ValueError):
                continue
    return rows


def _smooth(xs: list[float], k: int = 5) -> list[float]:
    """Simple centered moving average, robust to short series."""
    if not xs:
        return xs
    out = []
    for i in range(len(xs)):
        lo, hi = max(0, i - k // 2), min(len(xs), i + k // 2 + 1)
        out.append(sum(xs[lo:hi]) / (hi - lo))
    return out


def analyze(rows: list[dict]) -> dict:
    rows = sorted(rows, key=lambda r: r["step"])
    loss_pts = [(r["step"], r["train_loss"]) for r in rows if r["train_loss"] is not None]
    erc_pts  = [(r["step"], r["erc_pass_rate"]) for r in rows if r["erc_pass_rate"] is not None]

    if len(loss_pts) < 3 or len(erc_pts) < 2:
        return {"ok": False,
                "reason": f"insufficient data (loss pts={len(loss_pts)}, erc pts={len(erc_pts)})"}

    steps = [s for s, _ in loss_pts]
    losses = _smooth([v for _, v in loss_pts])
    start_loss, best_loss = losses[0], min(losses)
    descent = max(1e-9, start_loss - best_loss)
    # Plateau = first step where smoothed loss is within PLATEAU_TOL of its full descent.
    threshold = best_loss + PLATEAU_TOL * descent
    plateau_step = steps[-1]
    for s, lv in zip(steps, losses):
        if lv <= threshold:
            plateau_step = s
            break

    def erc_near(step_target, after: bool):
        cands = [(s, v) for s, v in erc_pts if (s >= step_target if after else s <= step_target)]
        if not cands:
            cands = erc_pts
        # nearest in step to the target
        return min(cands, key=lambda sv: abs(sv[0] - step_target))[1]

    erc_at_plateau = erc_near(plateau_step, after=False)
    erc_final      = erc_pts[-1][1]
    erc_peak_step, erc_peak = max(erc_pts, key=lambda sv: sv[1])
    rise_after_plateau = erc_peak - erc_at_plateau if erc_peak_step >= plateau_step else 0.0

    return {
        "ok": True,
        "n_loss_points": len(loss_pts),
        "n_erc_points": len(erc_pts),
        "start_loss": round(start_loss, 4),
        "best_loss": round(best_loss, 4),
        "plateau_step": int(plateau_step),
        "erc_at_plateau": round(erc_at_plateau, 4),
        "erc_final": round(erc_final, 4),
        "erc_peak": round(erc_peak, 4),
        "erc_peak_step": int(erc_peak_step),
        "rise_after_plateau": round(rise_after_plateau, 4),
        "grokking_signature": bool(rise_after_plateau >= GROK_MIN_RISE),
    }


def _maybe_plot(rows: list[dict], res: dict, out_png: Path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        print("[plot] matplotlib unavailable - skipping PNG")
        return
    rows = sorted(rows, key=lambda r: r["step"])
    ls = [(r["step"], r["train_loss"]) for r in rows if r["train_loss"] is not None]
    es = [(r["step"], r["erc_pass_rate"]) for r in rows if r["erc_pass_rate"] is not None]
    fig, ax1 = plt.subplots(figsize=(9, 5))
    ax1.plot([s for s, _ in ls], [v for _, v in ls], color="tab:red", label="train loss")
    ax1.set_xlabel("training step"); ax1.set_ylabel("train loss", color="tab:red")
    ax2 = ax1.twinx()
    ax2.plot([s for s, _ in es], [v for _, v in es], color="tab:blue", marker="o", label="ERC pass-rate")
    ax2.set_ylabel("ERC pass-rate", color="tab:blue"); ax2.set_ylim(0, 1)
    if res.get("ok"):
        ax1.axvline(res["plateau_step"], color="gray", ls="--", alpha=0.7)
        ax1.text(res["plateau_step"], ax1.get_ylim()[1]*0.9, " loss plateau", color="gray")
    plt.title("Grokking signature: ERC pass-rate vs train loss")
    fig.tight_layout(); fig.savefig(out_png, dpi=120); plt.close(fig)
    print(f"[plot] wrote {out_png.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run", help="wandb run path ENTITY/PROJECT/RUN_ID")
    g.add_argument("--csv", help="CSV with columns step, train_loss, erc_pass_rate")
    args = ap.parse_args()

    rows = _from_wandb(args.run) if args.run else _from_csv(args.csv)
    print(f"Loaded {len(rows)} history points")
    res = analyze(rows)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    (REPORT_DIR / f"grokking_{ts}.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    with open(REPORT_DIR / f"grokking_{ts}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["step", "train_loss", "erc_pass_rate"])
        for r in sorted(rows, key=lambda r: r["step"]):
            w.writerow([r["step"], r["train_loss"], r["erc_pass_rate"]])

    if not res.get("ok"):
        print("Analysis inconclusive:", res.get("reason"))
        (REPORT_DIR / f"grokking_{ts}.md").write_text(
            f"# Grokking analysis - inconclusive\n\n{res.get('reason')}\n", encoding="utf-8")
        return

    verdict = ("GROKKING SIGNATURE DETECTED" if res["grokking_signature"]
               else "no clear post-plateau rise (not grokking by this threshold)")
    md = "\n".join([
        f"# Grokking signature - {ts}",
        "",
        f"**Verdict: {verdict}**",
        "",
        f"- Train loss descended {res['start_loss']} -> {res['best_loss']}, "
        f"plateauing around **step {res['plateau_step']}**.",
        f"- ERC pass-rate at the plateau: **{100*res['erc_at_plateau']:.0f}%**.",
        f"- ERC pass-rate peak: **{100*res['erc_peak']:.0f}%** at step {res['erc_peak_step']}.",
        f"- Rise AFTER the loss plateau: **{100*res['rise_after_plateau']:+.0f} pts**.",
        f"- ERC pass-rate at end of run: {100*res['erc_final']:.0f}%.",
        "",
        "Interpretation: a positive rise after the loss plateau means the model kept "
        "improving on held-out circuits after it stopped reducing training loss - i.e. it "
        "generalized the circuit-construction rules rather than memorizing the data.",
        "",
    ])
    (REPORT_DIR / f"grokking_{ts}.md").write_text(md, encoding="utf-8")
    _maybe_plot(rows, res, REPORT_DIR / f"grokking_{ts}.png")
    print("\n" + md)


if __name__ == "__main__":
    main()
