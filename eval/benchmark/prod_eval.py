"""
prod_eval.py — production-path evaluation (the REAL product metric).

Drives the ACTUAL production pipeline (inference.pipeline.OhmaticPipeline) on the held-out
set — same code, same system prompt, same ERC-feedback format, same greedy decoding that
serving uses. So eval == prod, byte-for-byte; there is no parallel re-implementation here.

The pipeline runs: generate -> ERC check -> (if invalid) feed errors back -> correct ...
up to max_shots. We report pass@k by partition:
    pass@1            = single-shot generation (comparable to the in-training ERC, the 50%)
    pass@1 -> pass@k  = the lift from CORRECTION (the loopback scope; the "2 shots irl")

Held-out prompts are already in the normalized (T5-output) form Qwen trains on, so the
pipeline's normalizer stage is a pass-through (no T5 loaded).

Usage (on a GPU pod):
    python eval/benchmark/prod_eval.py --adapter VittoriaLanzo/ohmatic-qwen3-adapter \
        --revision best-erc --n 96 --max-shots 3 --out results/prod_eval.json
"""
from __future__ import annotations
import os, sys, json, time, argparse
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
from inference.pipeline import OhmaticPipeline, PipelineConfig


def _load_items(repo: str, token: str | None, n: int) -> list:
    """Deterministic, partition-proportional subset of the forward held-out benchmark."""
    from huggingface_hub import hf_hub_download
    p = hf_hub_download(repo, "data/holdout_v1.jsonl", repo_type="dataset", token=token)
    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    rows.sort(key=lambda r: r.get("prompt_sha1", r["prompt"]))
    if n and n < len(rows):
        by = defaultdict(list)
        for r in rows:
            by[r.get("partition", "?")].append(r)
        out = []
        for part in sorted(by):
            grp = by[part]
            out.extend(grp[:max(1, round(n * len(grp) / len(rows)))])
        rows = out[:n]
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True, help="HF repo id or local dir of the LoRA adapter")
    ap.add_argument("--revision", default="")
    ap.add_argument("--base", default="Qwen/Qwen3-8B")
    ap.add_argument("--dataset-repo", default="VittoriaLanzo/Ohmatic")
    ap.add_argument("--n", type=int, default=96)
    ap.add_argument("--max-shots", type=int, default=3, help="total attempts (1 generate + N-1 corrections)")
    ap.add_argument("--out", default="results/prod_eval.json")
    ap.add_argument("--save-traces", action="store_true", default=False,
                    help="Harvest per-shot loop traces (broken->feedback->fixed) alongside the eval.")
    ap.add_argument("--traces-out", default="results/prod_eval_traces.jsonl",
                    help="Path for the JSONL trace file (default: results/prod_eval_traces.jsonl).")
    args = ap.parse_args()

    token = os.environ.get("HF_TOKEN")
    items = _load_items(args.dataset_repo, token, args.n)
    print(f"Loaded {len(items)} held-out items. Building prod pipeline "
          f"(base={args.base}, adapter={args.adapter}@{args.revision or 'main'}) ...", flush=True)

    # The SAME pipeline prod serves. t5_model_id="" -> pass-through normalizer (held-out
    # prompts are already normalized). max_retries = max_shots-1 (initial + corrections).
    cfg = PipelineConfig(
        t5_model_id="",
        qwen_model_id=args.base,
        qwen_adapter_id=args.adapter,
        qwen_adapter_revision=args.revision,
        max_retries=max(0, args.max_shots - 1),
    )
    pipeline = OhmaticPipeline.from_config(cfg)

    # wandb — LIVE pass@k graphs (overall + per partition), logged per prompt. Robust: a wandb
    # failure must never take down the eval. Same project/entity as the training runs.
    _wb = False
    try:
        import wandb
        wandb.init(project="ohmatic-qwen3", entity="vittoria3103-123-no-company",
                   name=f"prodeval-{(args.revision or 'main')}-n{args.n}-s{args.max_shots}",
                   config={"adapter": args.adapter, "revision": args.revision or "main",
                           "base": args.base, "n": args.n, "max_shots": args.max_shots,
                           "eval": "prod_loop"})
        _wb = True
        print("[wandb] logging live to ohmatic-qwen3", flush=True)
    except Exception as e:
        print(f"[wandb] disabled ({e})", flush=True)

    max_shots = args.max_shots
    by_part = defaultdict(lambda: {"total": 0, **{f"pass@{k}": 0 for k in range(1, max_shots + 1)}})
    detail = []
    t0 = time.time()
    outp = ROOT / args.out
    outp.parent.mkdir(parents=True, exist_ok=True)
    interval = max(1, len(items) // 5)   # checkpoint every ~1/5 of the run

    # Traces file — opened once and written line by line so a mid-run crash loses nothing.
    traces_outp = ROOT / args.traces_out
    if args.save_traces:
        traces_outp.parent.mkdir(parents=True, exist_ok=True)
        _traces_fh = open(traces_outp, "w", encoding="utf-8")
    else:
        _traces_fh = None

    def _build_summary(done):
        agg = {"total": 0, **{f"pass@{k}": 0 for k in range(1, max_shots + 1)}}
        for d in by_part.values():
            for kk, vv in d.items():
                agg[kk] += vv
        def rate(d, k): return round(d[f"pass@{k}"] / d["total"], 4) if d["total"] else None
        return {
            "adapter": args.adapter, "revision": args.revision or "main",
            "n": agg["total"], "n_target": len(items), "done": done,
            "complete": done >= len(items),
            "max_shots": max_shots, "elapsed_min": round((time.time() - t0) / 60, 1),
            "overall": {f"pass@{k}": rate(agg, k) for k in range(1, max_shots + 1)},
            "by_partition": {p: {**{f"pass@{k}": rate(d, k) for k in range(1, max_shots + 1)},
                                 "n": d["total"]} for p, d in by_part.items()},
        }

    def _checkpoint(done):
        """Write partial results locally AND upload to HF, so a crash/kill never loses the
        completed work. Called every 1/5 of the run + at the end."""
        summary = _build_summary(done)
        outp.write_text(json.dumps({"summary": summary, "detail": detail}, indent=2), encoding="utf-8")
        try:
            from huggingface_hub import HfApi
            api = HfApi(token=os.environ.get("HF_TOKEN"))
            api.upload_file(
                path_or_fileobj=str(outp), path_in_repo="results/prod_eval.json",
                repo_id=args.dataset_repo, repo_type="dataset")
            print(f"  [checkpoint] {done}/{len(items)} uploaded  "
                  f"pass@1={summary['overall'].get('pass@1')} "
                  f"pass@{max_shots}={summary['overall'].get(f'pass@{max_shots}')}", flush=True)
            # Upload traces file alongside results when --save-traces is active.
            if args.save_traces and _traces_fh is not None:
                try:
                    _traces_fh.flush()
                    api.upload_file(
                        path_or_fileobj=str(traces_outp),
                        path_in_repo="results/prod_eval_traces.jsonl",
                        repo_id=args.dataset_repo, repo_type="dataset")
                    print(f"  [checkpoint] traces uploaded ({traces_outp.name})", flush=True)
                except Exception as te:
                    print(f"  [checkpoint] traces HF upload failed (local saved): {te}", flush=True)
        except Exception as e:
            print(f"  [checkpoint] HF upload failed (local saved): {e}", flush=True)
        return summary

    def _wandb_log(done):
        if not _wb:
            return
        try:
            s = _build_summary(done)
            d = {"done": done}
            for kk, vv in s["overall"].items():
                if vv is not None:
                    d[f"overall/{kk}"] = vv
            for part, pv in s["by_partition"].items():
                for kk, vv in pv.items():
                    if kk.startswith("pass@") and vv is not None:
                        d[f"{part}/{kk}"] = vv
            wandb.log(d, step=done)
        except Exception as e:
            print(f"[wandb] log failed: {e}", flush=True)

    for i, it in enumerate(items):
        part = it.get("partition", "?")
        by_part[part]["total"] += 1
        result = pipeline.run(it["prompt"], return_trace=args.save_traces)
        # result.attempts is the attempt the circuit passed at (ok), else max_retries+1.
        passed_at = result.attempts if result.ok else None
        if passed_at:
            for k in range(passed_at, max_shots + 1):
                by_part[part][f"pass@{k}"] += 1
        detail.append({"id": it.get("id"), "partition": part,
                       "ok": result.ok, "passed_at": passed_at,
                       # capture the ERC rule codes still failing (the weakness map) so we keep
                       # the FULL pass/fail picture, not just the count
                       "fail_rules": sorted({e.get("code") for e in (result.erc_errors or [])
                                             if e.get("code")}) if not result.ok else []})
        # Write trace line — never crash the eval on trace errors.
        if args.save_traces and _traces_fh is not None:
            try:
                trace_line = json.dumps({
                    "id": it.get("id"),
                    "partition": part,
                    "prompt": it["prompt"],
                    "ok": result.ok,
                    "passed_at": passed_at,
                    "trace": result.trace,
                }, ensure_ascii=False)
                _traces_fh.write(trace_line + "\n")
            except Exception as te:
                print(f"[traces] write failed for item {it.get('id')}: {te}", flush=True)
        _wandb_log(i + 1)
        if (i + 1) % interval == 0 and (i + 1) < len(items):
            _checkpoint(i + 1)

    summary = _checkpoint(len(items))
    if _traces_fh is not None:
        try:
            _traces_fh.close()
        except OSError:
            pass  # best-effort flush/close of the trace file; eval summary already computed
    print("\n=== PRODUCTION EVAL (eval == prod pipeline) ===")
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {outp}")
    if _wb:
        try:
            for kk, vv in summary["overall"].items():
                if vv is not None:
                    wandb.run.summary[f"final/{kk}"] = vv
            wandb.finish()
        except Exception:
            pass  # wandb finalization is best-effort telemetry; never fail the eval on it


if __name__ == "__main__":
    main()
