"""ERC golden regression - the refactor safety net.

Asserts analyze_schematic produces IDENTICAL diagnostic codes on a frozen
182-circuit fixture, so any drift in the ERC engine (the verifier behind training,
prod, and the benchmark) fails loudly. The fixture holds PRIVATE holdout circuits,
so it is gitignored and built locally; without it the test SKIPS (CI-safe).
"""

import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "erc_golden.jsonl"


@pytest.mark.skipif(not FIXTURE.exists(), reason="local-only golden fixture absent")
def test_erc_golden_identical():
    from eval.diagnostics import analyze_schematic
    rows = [json.loads(l) for l in FIXTURE.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    assert len(rows) >= 100
    drift = []
    for r in rows:
        diags = analyze_schematic(r["circuit"]).get("diagnostics", [])
        codes = sorted(d.get("code", "?") for d in diags)
        if codes != r["codes"]:
            drift.append((r["sig"], r["codes"], codes))
    assert not drift, f"ERC behavior drifted on {len(drift)} circuits: {drift[:3]}"
