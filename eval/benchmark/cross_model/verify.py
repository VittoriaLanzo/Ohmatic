"""Stage 2 - VERIFY (local, free, rerunnable forever).

    python -m eval.benchmark.cross_model.verify

Classifies every results/{model}.jsonl row through the IDENTICAL extraction -> ERC
path (analyze_schematic, the single source of truth shared with training and prod).
Outcomes:
    delivered_clean     circuit reached the user and passes ERC
    delivered_broken    circuit reached the user and FAILS ERC (hosted legs have no
                        killswitch so all ERC failures land here; for Ohmatic = GATE BUG)
    blocked_killswitch  Ohmatic refused: no unverified circuit delivered
    invalid_output      nothing extractable as a circuit (hosted legs)

Generate and verify never touch, so an extraction-bug fix reruns free, no API dollar respent.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval.benchmark.cross_model import config as C
from eval.diagnostics import analyze_schematic   # SINGLE source of truth


def extract_circuit(text: str) -> dict | None:
    """Shared lenient extractor - applied to EVERY model equally.
    Strips markdown fences / prose, takes the first balanced top-level {...}."""
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    while start != -1:                      # first balanced object
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        break
                    break
        start = text.find("{", start + 1)
    return None


def erc_pass(circuit: dict) -> tuple[bool, list[dict]]:
    diags = analyze_schematic(circuit).get("diagnostics", [])
    return (not diags), diags


def classify(row: dict) -> dict:
    """-> {"outcome": ..., "n_diags": int, "diag_codes": [...]}"""
    if "ok" in row:                                    # Ohmatic pipeline leg
        if row.get("blocked") or not row.get("ok"):
            return {"outcome": "blocked_killswitch", "n_diags": 0, "diag_codes": []}
        circuit = extract_circuit(row.get("delivered_circuit_json", ""))
        if circuit is None:                            # should be impossible
            return {"outcome": "delivered_broken", "n_diags": -1,
                    "diag_codes": ["UNPARSEABLE_DELIVERY"]}
        ok, diags = erc_pass(circuit)                  # independent re-check
        return {"outcome": "delivered_clean" if ok else "delivered_broken",
                "n_diags": len(diags),
                "diag_codes": sorted({d.get("code", "?") for d in diags})}

    circuit = extract_circuit(row.get("raw_output", ""))   # hosted leg
    if circuit is None:
        return {"outcome": "invalid_output", "n_diags": -1, "diag_codes": []}
    ok, diags = erc_pass(circuit)
    return {"outcome": "delivered_clean" if ok else "delivered_broken",
            "n_diags": len(diags),
            "diag_codes": sorted({d.get("code", "?") for d in diags})}


def main() -> None:
    C.VERIFIED_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for path in sorted(C.RESULTS_DIR.glob("*.jsonl")):
        out_path = C.VERIFIED_DIR / path.name
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8")
                .splitlines() if l.strip()]
        with open(out_path, "w", encoding="utf-8") as fh:
            for r in rows:
                v = classify(r)
                keep = {k: r.get(k) for k in
                        ("model", "suite", "prompt_id", "category", "attempts",
                         "latency_s", "tokens_in", "tokens_out", "cost_usd")}
                fh.write(json.dumps({**keep, **v}, ensure_ascii=False) + "\n")
        total += len(rows)
        print(f"verified {len(rows):4d} rows -> {out_path}")
    print(f"done: {total} rows. Run report.py for the tables.")


if __name__ == "__main__":
    main()
