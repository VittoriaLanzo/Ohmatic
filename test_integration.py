#!/usr/bin/env python3
"""Quick integration test — no external dependencies needed."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dataset.validate import SchemaValidator
from inference.model import load_model
from ui.renderer import SchematicRenderer

errors = []

# 1. Validate all 20 seed circuits
with open("dataset/examples.json") as f:
    examples = json.load(f)
v = SchemaValidator()
ok = sum(1 for c in examples if v.validate_circuit(c))
assert ok == 20, f"Validation: only {ok}/20 valid"
print(f"[OK] dataset/validate.py  — {ok}/20 circuits valid")

# 2. Mock model generates a valid circuit
model = load_model(use_mock=True)
circuit = model.generate_circuit("test")
assert circuit and "metadata" in circuit and "components" in circuit and "nets" in circuit
assert v.validate_circuit(circuit), f"Mock output invalid: {v.get_errors()}"
print(f"[OK] inference/model.py   — mock generates '{circuit['metadata']['title']}'")

# 3. SVG renderer produces SVG for every circuit
renderer = SchematicRenderer()
for i, c in enumerate(examples):
    svg = renderer.render(c)
    assert svg.startswith("<svg"), f"Circuit {i} render failed"
print(f"[OK] ui/renderer.py       — rendered all 20 circuits to SVG")

# 4. Import all public modules (training skipped — requires pip install datasets)
from dataset.generate import CircuitGenerator
from inference.cli import generate_circuit_cli
try:
    from training.prepare_dataset import create_prompts, create_dataset
    print("[OK] all imports           — no ImportError")
except ModuleNotFoundError as e:
    print(f"[--] training.prepare_dataset skipped — {e} (pip install datasets)")

print("\nAll integration checks passed!")
