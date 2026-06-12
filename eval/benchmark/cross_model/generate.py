"""
Stage 1 - GENERATE (the only stage that costs money).
======================================================
    python -m eval.benchmark.cross_model.generate --model star-r2-bf16 --suite forward
    python -m eval.benchmark.cross_model.generate --model fable-5 --suite realuser --n 20

Append-only JSONL per model: results/{model}.jsonl. Rows are keyed
(model, suite, prompt_id) - reruns SKIP completed keys, so any crash or
rate-limit resumes without double-paying. Raw outputs are stored verbatim;
verification happens in stage 2 (verify.py) for free, forever.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval.benchmark.cross_model import config as C
from eval.benchmark.cross_model.adapters import build_adapter
from eval.benchmark.cross_model.prompts import load_suite


def _done_keys(path: Path) -> set[tuple[str, str]]:
    done = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["suite"], r["prompt_id"]))
    return done


def _cost(model: str, tin: int, tout: int) -> float:
    pin, pout = C.PRICES.get(model, (0.0, 0.0))
    return round((tin * pin + tout * pout) / 1e6, 6)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=list(C.MODELS))
    ap.add_argument("--suite", required=True, choices=list(C.SUITES))
    ap.add_argument("--n", type=int, default=0,
                    help="forward/realuser: cap items; correction: per-category cap")
    ap.add_argument("--dry-run", action="store_true",
                    help="list pending items, build nothing, spend nothing")
    args = ap.parse_args()

    C.check_suite_allowed(args.model, args.suite)
    items = load_suite(args.suite, args.n)

    C.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = C.RESULTS_DIR / f"{args.model}.jsonl"
    done = _done_keys(out_path)
    pending = [it for it in items if (it["suite"], it["prompt_id"]) not in done]
    print(f"[{args.model}/{args.suite}] items={len(items)} done={len(items)-len(pending)} "
          f"pending={len(pending)}", flush=True)
    if args.dry_run or not pending:
        return

    # System prompt: the SHARED single source - byte-identical for every leg.
    from shared.prompt_builder import build_system_prompt
    system_prompt = build_system_prompt()

    adapter = build_adapter(args.model, args.suite)

    n_err = 0
    with open(out_path, "a", encoding="utf-8") as fh:
        for i, it in enumerate(pending, 1):
            try:
                if it.get("messages"):            # correction: verbatim trained convo
                    if not hasattr(adapter, "chat_messages"):
                        raise SystemExit("correction suite requires a local leg")
                    frag = adapter.chat_messages(it["messages"])
                else:
                    user = it["user_prompt"]
                    if it["system_extra"]:
                        user = f"{user}\n\n{it['system_extra']}"
                    frag = adapter.run(system_prompt, user)
            except Exception as exc:              # transient API error: skip, resume later
                n_err += 1
                print(f"  [{i}/{len(pending)}] {it['prompt_id']} ERROR: {exc}", flush=True)
                if n_err >= 5:
                    print("5 consecutive-ish errors - stopping (resume later).", flush=True)
                    break
                time.sleep(10)
                continue
            n_err = 0
            row = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "model": args.model,
                "suite": it["suite"],
                "prompt_id": it["prompt_id"],
                "category": it["category"],
                "cost_usd": _cost(args.model, frag.get("tokens_in", 0),
                                  frag.get("tokens_out", 0)),
                **frag,
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            tag = ("ok" if frag.get("ok") else
                   "BLOCKED" if frag.get("blocked") else f"{len(frag.get('raw_output',''))}ch")
            print(f"  [{i}/{len(pending)}] {it['prompt_id']} {tag} "
                  f"{frag['latency_s']}s", flush=True)

    print(f"[{args.model}/{args.suite}] stage-1 complete -> {out_path}", flush=True)


if __name__ == "__main__":
    main()
