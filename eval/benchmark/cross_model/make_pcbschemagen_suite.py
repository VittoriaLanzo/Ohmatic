"""Build the `pcbschemagen` suite from PCBSchemaGen's PCBBench tasks.

    python -m eval.benchmark.cross_model.make_pcbschemagen_suite

Source: PCBSchemaGen v2 (https://github.com/HZou9/PCBSchemaGen_v2), MIT-licensed
(c) 2026 Zou et al. We use ONLY `benchmarks/pcbbench/benchmark.tsv` - the 62
single-circuit tasks, which match Ohmatic's per-request granularity. The 165-task
Open-Schematics-Eval set is board-level (median ~8, up to 28 component types) and is
deliberately NOT used here: Ohmatic builds one focused circuit per request, not whole
multi-IC boards, so OSE would measure a granularity mismatch rather than circuit quality.

This is a THIRD-PARTY external-validity probe: their PROMPTS, OUR ERC. We do NOT score with
PCBSchemaGen's own verifier - that one rewards exact required-part matching (AMC1350, OPA328,
...), which would penalise Ohmatic for legitimately substituting from its family catalog.

Conversion (deterministic, so the suite is reproducible):
  * prompt    = the natural-language Task + a compact I/O spec line (rails/nodes), so the
                model gets the same constraints the PCBSchemaGen models were given. We do
                NOT inject their exact required-component BOM - Ohmatic builds from its own
                catalog and our ERC scores electrical soundness, not part identity.
  * category  = their `Type` field (Sensing, AuxPower, DC-DC, ...).
  * id        = "pcb-<Id>".
  * order     = round-robin by category, so a capped prefix (`generate --n K`) spans types.

If we ever redistribute the materialised suite, ship PCBSchemaGen's MIT LICENSE + copyright
notice alongside it and cite their paper (their BibTeX). The builder keeps that provenance
in this module so the obligation is impossible to lose.
"""

from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
from collections import OrderedDict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval.benchmark.cross_model import config as C

PCBBENCH_TSV_URL = (
    "https://raw.githubusercontent.com/HZou9/PCBSchemaGen_v2/main/"
    "benchmarks/pcbbench/benchmark.tsv"
)
OUT_FILE = C.DATA_DIR / "pcbschemagen_prompts.jsonl"


def _load_tsv(local: Path | None) -> list[dict]:
    if local and local.exists():
        text = local.read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(PCBBENCH_TSV_URL, timeout=60) as r:  # noqa: S310 (trusted host)
            text = r.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


def _render_prompt(row: dict) -> str:
    """Functional NL task + a compact I/O spec (no forced part BOM)."""
    spec = []
    if row.get("InputNodes"):
        spec.append(f"input {row['InputNodes']}"
                    + (f" at {row['InputVoltage']}V" if row.get("InputVoltage") else ""))
    if row.get("OutputNodes"):
        spec.append(f"output {row['OutputNodes']}"
                    + (f" at {row['OutputVoltage']}V" if row.get("OutputVoltage") else ""))
    prompt = (row.get("Task") or "").strip()
    if spec:
        prompt += "\n\n(" + "; ".join(spec) + ")"
    return prompt


def _stratify(items: list[dict]) -> list[dict]:
    """Round-robin by category so `generate --n K` gets a spread across circuit types."""
    buckets: OrderedDict[str, list[dict]] = OrderedDict()
    for it in items:
        buckets.setdefault(it["category"], []).append(it)
    out: list[dict] = []
    while any(buckets.values()):
        for cat in list(buckets):
            if buckets[cat]:
                out.append(buckets[cat].pop(0))
    return out


def build(local_tsv: Path | None = None) -> list[dict]:
    rows = _load_tsv(local_tsv)
    items = [{"id": f"pcb-{r['Id']}", "prompt": _render_prompt(r),
              "category": r.get("Type", "?")} for r in rows]
    items = _stratify(items)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in items) + "\n",
                        encoding="utf-8")
    return items


def main() -> None:
    local = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    items = build(local)
    from collections import Counter
    cats = Counter(x["category"] for x in items)
    print(f"wrote {len(items)} PCBBench tasks -> {OUT_FILE}")
    print(f"categories ({len(cats)}): " + ", ".join(f"{k}={v}" for k, v in cats.most_common()))
    print("source: PCBSchemaGen v2 (MIT, (c) 2026 Zou et al.) - cite on redistribution.")


if __name__ == "__main__":
    main()
