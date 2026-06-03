"""
verify_model.py — Marketing-grade verification of the Ohmatic fine-tune
========================================================================
Runs the FROZEN held-out benchmark (built by build_holdout.py) against BOTH the
base Qwen3-8B-Instruct and the fine-tuned adapter, and emits a one-page report with
every number traceable to a file. Run this on the pod after training (needs the GPU).

Metrics (computed for base AND fine-tune):
  parse_rate           response parses as a JSON object
  erc_pass_rate        parses AND passes the Ohmatic ERC engine
    - unseen_variant   pass-rate on unseen specs from trained families
    - novel_family     pass-rate on ENTIRELY unseen topologies (the grokking proof)
  generalization_gap   ERC pass on a trained-prompt sample minus held-out pass-rate
  loopback_repair_rate given a broken circuit + ERC errors, does the fix pass ERC?

The base vs fine-tune DELTA on the same frozen set is the whole pitch, and anyone
with the benchmark can reproduce it.

Usage (on the pod, after training):
    python eval/benchmark/verify_model.py \
        --adapter /workspace/ohmatic-checkpoints/best-erc-adapter

    # or pull the adapter from HF:
    python eval/benchmark/verify_model.py --adapter VittoriaLanzo/ohmatic-qwen3-adapter --adapter-revision best-erc
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.diagnostics import analyze_schematic

BASE_MODEL   = "Qwen/Qwen3-8B-Instruct"
DATASET_REPO = "VittoriaLanzo/Ohmatic"
REPORT_DIR   = ROOT / "eval" / "benchmark" / "reports"

# Local-first, HF-fallback paths for the frozen benchmark.
LOCAL_BENCH  = ROOT / "eval" / "benchmark" / "holdout_v1.jsonl"
LOCAL_LB     = ROOT / "eval" / "benchmark" / "holdout_loopback_v1.jsonl"
HF_BENCH     = "data/holdout_v1.jsonl"
HF_LB        = "data/holdout_loopback_v1.jsonl"
HF_EXCLUDE   = "data/holdout_exclude_hashes.txt"
HF_TRAINSET  = "data/qwen_training_all.jsonl"


# ── IO helpers ────────────────────────────────────────────────────────────────

def _hf_token() -> str:
    return os.environ.get("HF_TOKEN", "").strip()

def _read_jsonl(path: Path) -> list:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def _load_jsonl_anywhere(local: Path, hf_name: str) -> list:
    if local.exists():
        print(f"[data] local: {local.relative_to(ROOT)}")
        return _read_jsonl(local)
    from huggingface_hub import hf_hub_download
    p = hf_hub_download(repo_id=DATASET_REPO, filename=hf_name, repo_type="dataset", token=_hf_token())
    print(f"[data] HF: {hf_name}")
    return _read_jsonl(Path(p))

def _load_exclude_hashes() -> set:
    from huggingface_hub import hf_hub_download
    p = hf_hub_download(repo_id=DATASET_REPO, filename=HF_EXCLUDE, repo_type="dataset", token=_hf_token())
    return {ln.strip() for ln in Path(p).read_text().splitlines() if ln.strip()}

def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip().lower())

def _phash(t: str) -> str:
    import hashlib
    return hashlib.sha1(_norm(t).encode("utf-8")).hexdigest()


# ── Response parsing / scoring ────────────────────────────────────────────────

def _extract_json(response: str):
    """Strip code fences and parse the model output to a dict, or return None."""
    r = response.strip()
    if r.startswith("```"):
        parts = r.split("```")
        if len(parts) >= 2:
            r = parts[1]
            if r.startswith("json"):
                r = r[4:]
    r = r.strip()
    # Fallback: grab the first {...} balanced-ish span if there's trailing chatter.
    if not r.startswith("{"):
        i = r.find("{")
        if i >= 0:
            r = r[i:]
    try:
        obj = json.loads(r)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None

def _score(response: str) -> tuple[bool, bool]:
    """Return (parsed_ok, erc_pass)."""
    obj = _extract_json(response)
    if obj is None:
        return False, False
    try:
        res = analyze_schematic(obj.get("circuit", obj))
        return True, bool(res["valid"])
    except Exception:
        return True, False


# ── Model ─────────────────────────────────────────────────────────────────────

def load_models(adapter: str, adapter_revision: str | None):
    """Load base Qwen3 and wrap the adapter. disable_adapter() yields the true base,
    so base and fine-tune share identical base weights — a clean apples-to-apples test."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    tok = _hf_token() or None
    print(f"[model] loading base {BASE_MODEL} (bf16)...")
    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, torch_dtype=torch.bfloat16, device_map="auto", token=tok,
    )
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, token=tok)
    print(f"[model] attaching adapter: {adapter} (rev={adapter_revision})")
    model = PeftModel.from_pretrained(base, adapter, revision=adapter_revision, token=tok)
    model.eval()
    return model, tokenizer


def _build_prompt_text(tokenizer, messages: list) -> str:
    try:
        return tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False,
        )
    except TypeError:
        return tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
        )


def generate(model, tokenizer, messages: list, max_new_tokens: int = 1500) -> str:
    import torch
    text = _build_prompt_text(tokenizer, messages)
    inp = tokenizer(text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inp, max_new_tokens=max_new_tokens, do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    return tokenizer.decode(out[0][inp["input_ids"].shape[1]:], skip_special_tokens=True)


# ── Evaluation passes ─────────────────────────────────────────────────────────

def _eval_prompts(model, tokenizer, items: list, use_adapter: bool, label: str) -> list:
    """Generate + score one circuit per item. items: [{prompt, partition, ...}]."""
    from contextlib import nullcontext
    ctx = nullcontext() if use_adapter else model.disable_adapter()
    results = []
    with ctx:
        for i, it in enumerate(items):
            try:
                resp = generate(model, tokenizer, [{"role": "user", "content": it["prompt"]}])
                parsed, erc = _score(resp)
            except Exception as exc:
                print(f"  [{label}] item {i} generation error: {exc}")
                parsed, erc = False, False
            results.append({"partition": it.get("partition", "?"), "parsed": parsed, "erc": erc})
            if (i + 1) % 25 == 0:
                print(f"  [{label}] {i+1}/{len(items)}")
    return results


def _eval_loopback(model, tokenizer, cases: list, use_adapter: bool, label: str) -> dict:
    from contextlib import nullcontext
    ctx = nullcontext() if use_adapter else model.disable_adapter()
    fixed = 0
    with ctx:
        for i, c in enumerate(cases):
            try:
                resp = generate(model, tokenizer, c["input_messages"])
                _, erc = _score(resp)
                fixed += int(erc)
            except Exception:
                pass
    n = len(cases)
    return {"repaired": fixed, "total": n, "rate": (fixed / n) if n else 0.0}


def _summarize(results: list) -> dict:
    n = len(results)
    by_part = defaultdict(lambda: [0, 0])  # partition -> [erc_pass, total]
    parsed = erc = 0
    for r in results:
        parsed += int(r["parsed"])
        erc += int(r["erc"])
        by_part[r["partition"]][0] += int(r["erc"])
        by_part[r["partition"]][1] += 1
    out = {
        "n": n,
        "parse_rate": parsed / n if n else 0.0,
        "erc_pass_rate": erc / n if n else 0.0,
        "by_partition": {
            p: {"erc_pass_rate": c[0] / c[1] if c[1] else 0.0, "n": c[1]}
            for p, c in sorted(by_part.items())
        },
    }
    return out


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True,
                    help="Local adapter dir OR HF repo id of the fine-tuned adapter.")
    ap.add_argument("--adapter-revision", default=None, help="HF branch/revision (e.g. best-erc).")
    ap.add_argument("--train-sample", type=int, default=100,
                    help="N trained prompts to measure the generalization gap (0 to skip).")
    ap.add_argument("--limit", type=int, default=0, help="Cap benchmark items (debug).")
    args = ap.parse_args()

    bench = _load_jsonl_anywhere(LOCAL_BENCH, HF_BENCH)
    lb    = _load_jsonl_anywhere(LOCAL_LB, HF_LB)
    if args.limit:
        bench = bench[: args.limit]
        lb = lb[: args.limit]
    print(f"Benchmark: {len(bench)} prompts, {len(lb)} loopback cases")

    # Trained-prompt sample for the generalization gap (prompts NOT in the exclude set).
    train_items = []
    if args.train_sample > 0:
        try:
            excl = _load_exclude_hashes()
            train_rows = _load_jsonl_anywhere(Path("/nonexistent"), HF_TRAINSET)
            import random
            rng = random.Random(7)
            rng.shuffle(train_rows)
            for r in train_rows:
                p = r["messages"][1]["content"]
                if _phash(p) not in excl:
                    train_items.append({"prompt": p, "partition": "trained"})
                if len(train_items) >= args.train_sample:
                    break
            print(f"Trained-prompt sample for gap: {len(train_items)}")
        except Exception as exc:
            print(f"[warn] could not build trained sample (gap skipped): {exc}")

    model, tokenizer = load_models(args.adapter, args.adapter_revision)

    report = {"created_utc": datetime.now(timezone.utc).isoformat(),
              "base_model": BASE_MODEL, "adapter": args.adapter,
              "adapter_revision": args.adapter_revision}

    for use_adapter, key in [(False, "base"), (True, "fine_tune")]:
        print(f"\n=== Evaluating: {key} ===")
        held = _eval_prompts(model, tokenizer, bench, use_adapter, key)
        summ = _summarize(held)
        summ["loopback_repair"] = _eval_loopback(model, tokenizer, lb, use_adapter, key)
        if train_items:
            tr = _summarize(_eval_prompts(model, tokenizer, train_items, use_adapter, f"{key}-train"))
            summ["trained_sample_erc_pass_rate"] = tr["erc_pass_rate"]
            summ["generalization_gap"] = tr["erc_pass_rate"] - summ["erc_pass_rate"]
        report[key] = summ

    _write_report(report)


def _pct(x: float) -> str:
    return f"{100*x:.1f}%"

def _write_report(report: dict):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    (REPORT_DIR / f"report_{ts}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    b, f = report["base"], report["fine_tune"]
    def row(name, bk, fk):
        return f"| {name} | {_pct(bk)} | {_pct(fk)} | {_pct(fk-bk):>+7} |"

    lines = [
        f"# Ohmatic verification report — {report['created_utc']}",
        "",
        f"- Base model: `{report['base_model']}`",
        f"- Adapter: `{report['adapter']}` (rev: `{report['adapter_revision']}`)",
        f"- Benchmark: {b['n']} held-out prompts (frozen, never trained on)",
        "",
        "| Metric | Base | Fine-tune | Δ |",
        "|---|---|---|---|",
        row("ERC pass-rate (overall)", b["erc_pass_rate"], f["erc_pass_rate"]),
        row("JSON parse-rate", b["parse_rate"], f["parse_rate"]),
    ]
    for part in sorted(set(b["by_partition"]) | set(f["by_partition"])):
        bp = b["by_partition"].get(part, {}).get("erc_pass_rate", 0.0)
        fp = f["by_partition"].get(part, {}).get("erc_pass_rate", 0.0)
        npart = f["by_partition"].get(part, {}).get("n", 0)
        lines.append(row(f"ERC pass — {part} (n={npart})", bp, fp))
    lines.append(row("Loopback repair-rate",
                     b["loopback_repair"]["rate"], f["loopback_repair"]["rate"]))
    if "generalization_gap" in f:
        lines += [
            "",
            f"- Trained-sample ERC pass-rate (fine-tune): {_pct(f['trained_sample_erc_pass_rate'])}",
            f"- **Generalization gap** (trained − held-out): {_pct(f['generalization_gap'])} "
            "(smaller = generalized rather than memorized)",
        ]
    lines += [
        "",
        "## Honest reading",
        "- `novel_family` is the strongest claim: ERC pass-rate on circuit topologies "
        "entirely absent from training.",
        "- A small generalization gap + `novel_family` lift over base = evidence the model "
        "learned the rules, not the examples.",
        "- Every number above is reproducible: same frozen benchmark, `do_sample=False` (greedy).",
        "",
    ]
    md = "\n".join(lines)
    out_md = REPORT_DIR / f"report_{ts}.md"
    out_md.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"\nReport written: {out_md.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
