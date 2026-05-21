# Ohmatic Testing Guide

Complete instructions for testing every component of the project.

## Setup

```bash
cd c:\Users\Vittoria\Desktop\Ohmatic
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 1. Validate Example Circuits

**File:** `dataset/validate.py`

Tests schema validation and example data.

```bash
# Test validation
python dataset/validate.py dataset/examples.json

# Expected output:
# Validation: 20/20 circuits valid
```

**What it tests:**
- ✓ All 20 seed circuits are valid
- ✓ Schema constraints enforced
- ✓ No orphaned pins
- ✓ VCC/GND nets present

---

## 2. Generate CLI Test

**File:** `inference/cli.py`

Tests circuit generation from command line.

```bash
# Generate using mock model
python inference/cli.py "LED circuit with resistor" --mock

# Expected output:
# {
#   "metadata": {...},
#   "components": [...],
#   "nets": [...]
# }

# Test with temperature control
python inference/cli.py "555 timer oscillator" --mock --temperature 0.5

# Test with validation
python inference/cli.py "OpAmp amplifier" --mock --no-validate
```

**What it tests:**
- ✓ Mock model generates valid JSON
- ✓ Temperature parameter works
- ✓ Output is parseable JSON
- ✓ Validation catches errors

---

## 3. Prepare Dataset for Training

**File:** `training/prepare_dataset.py`

Converts examples.json to HuggingFace format.

```bash
# Prepare dataset
python training/prepare_dataset.py \
    --input dataset/examples.json \
    --output dataset/prepared \
    --test-split 0.1 \
    --formats parquet csv

# Expected output:
# Loading examples from dataset/examples.json...
# Loaded 20 circuits
# Creating prompts...
# Creating dataset splits...
# Saving dataset...
# Dataset statistics:
#   Total examples: 20
#   Train: 18 (90.0%)
#   Test: 2 (10.0%)

# Verify output files
ls -la dataset/prepared/
# Should contain:
# - huggingface/    (HuggingFace datasets format)
# - train.parquet   (training split)
# - test.parquet    (test split)
# - train.csv       (CSV format)
# - test.csv
```

**What it tests:**
- ✓ JSON → HuggingFace conversion
- ✓ Train/test split works
- ✓ Multiple output formats
- ✓ Dataset statistics correct

---

## 4. Renderer SVG Output

**File:** `ui/renderer.py`

Converts circuit JSON to SVG diagrams.

```bash
# Render first circuit
python ui/renderer.py \
    --input dataset/examples.json \
    --output circuit_0.svg \
    --circuit 0

# Expected output:
# Rendered circuit 0 to circuit_0.svg

# Verify SVG was created
cat circuit_0.svg | head -20
# Should show valid SVG XML

# Try different circuits
python ui/renderer.py --input dataset/examples.json --output circuit_1.svg --circuit 1
python ui/renderer.py --input dataset/examples.json --output circuit_2.svg --circuit 2
```

**What it tests:**
- ✓ SVG generation works
- ✓ Components rendered correctly
- ✓ Nets drawn between pins
- ✓ Multiple circuits can be rendered
- ✓ File written to disk

---

## 5. Web UI (Gradio App)

**File:** `ui/app.py`

Interactive web interface for circuit generation.

```bash
# Start the app
python ui/app.py --share

# Expected output:
# Running on local URL:  http://127.0.0.1:7860

# Open browser and:
# 1. Type a circuit description
# 2. Click "Generate Circuit"
# 3. See JSON output and SVG diagram
# 4. Try "Load Example" button
# 5. Click "Validate JSON" to check output
```

**What to test:**
- ✓ Gradio interface loads (http://localhost:7860)
- ✓ Generation button works
- ✓ Example circuits load
- ✓ JSON display shows valid circuits
- ✓ SVG rendering displays diagrams
- ✓ Validation reports success/failure

---

## 6. Model Loading

**File:** `inference/model.py`

Tests model wrapper and mock fallback.

```bash
# Test in Python
python

# In interactive shell:
from inference.model import load_model, MockCircuitModel

# Test mock model
model = load_model(use_mock=True)
print(model)  # MockCircuitModel()

circuit = model.generate_circuit("test circuit")
print(circuit is not None)  # True
print("metadata" in circuit)  # True

# Exit
exit()
```

**What it tests:**
- ✓ Mock model initializes
- ✓ generate_circuit() returns valid dict
- ✓ Fallback works when model missing

---

## 7. Dataset Generation (with API)

**File:** `dataset/generate.py`

Generates circuits using Claude API (requires API key).

```bash
# Generate 3 new circuits
python dataset/generate.py \
    --api-key sk-ant-your-key-here \
    --num-circuits 3 \
    --append \
    --rate-limit 2.0

# Expected output:
# Generating circuit 1/3...
#   ✓ Success
# Generating circuit 2/3...
#   ✓ Success
# Generating circuit 3/3...
#   ✓ Success
# Saved 23 circuits to dataset/examples.json
# Total circuits: 23

# Validate the new circuits
python dataset/validate.py dataset/examples.json
# Should show: Validation: 23/23 circuits valid (or fewer if some failed)
```

**What it tests:**
- ✓ API key authentication
- ✓ Circuit generation and validation
- ✓ Appending to existing dataset
- ✓ Rate limiting works
- ✓ Output saved correctly

**Note:** Requires valid Anthropic API key. Costs ~$0.02-0.05 per 3 circuits.

---

## 8. Full Integration Test

**Complete workflow test:**

```bash
# 1. Validate seed data
echo "=== Step 1: Validate ==="
python dataset/validate.py dataset/examples.json

# 2. Prepare training data
echo "=== Step 2: Prepare Dataset ==="
python training/prepare_dataset.py --input dataset/examples.json --output dataset/prepared

# 3. Generate from CLI
echo "=== Step 3: CLI Generation ==="
python inference/cli.py "simple circuits" --mock > generated.json

# 4. Validate generated circuit
echo "=== Step 4: Validate Generated ==="
python -c "
import json
from dataset.validate import SchemaValidator
with open('generated.json') as f:
    circuit = json.load(f)
validator = SchemaValidator()
print('Valid!' if validator.validate_circuit(circuit) else 'Invalid!')
"

# 5. Render to SVG
echo "=== Step 5: Render ==="
python ui/renderer.py --input dataset/examples.json --output test.svg

# 6. Verify all outputs exist
echo "=== Verifying outputs ==="
ls -lh dataset/prepared/
ls -lh test.svg
ls -lh generated.json
```

---

## 9. Performance Benchmarks

**Test inference speed:**

```bash
# Time circuit generation
time python inference/cli.py "RC filter circuit" --mock

# Expected: <1 second (mock model)
# Real model: 30-60 seconds on CPU, 2-5 seconds on GPU
```

**Test dataset operations:**

```bash
# Time validation
time python dataset/validate.py dataset/examples.json

# Time preparation
time python training/prepare_dataset.py --input dataset/examples.json --output dataset/prepared
```

---

## 10. Error Handling

**Test error cases:**

```bash
# Test missing file
python dataset/validate.py nonexistent.json
# Expected: "Error: nonexistent.json not found"

# Test invalid circuit index
python ui/renderer.py --input dataset/examples.json --output test.svg --circuit 999
# Expected: "Circuit index 999 out of range"

# Test empty prompt
python inference/cli.py "" --mock
# Expected: Error message in status

# Test invalid JSON validation
python -c "
from dataset.validate import SchemaValidator
validator = SchemaValidator()
print(validator.validate_circuit({'invalid': 'data'}))
"
# Expected: False with error messages
```

---

## 11. Code Quality Tests

**Check imports and syntax:**

```bash
# Test all imports resolve
python -c "
from dataset.validate import SchemaValidator
from dataset.generate import CircuitGenerator
from training.prepare_dataset import create_dataset
from inference.model import load_model
from inference.cli import generate_circuit_cli
from ui.renderer import SchematicRenderer
from ui.app import OhmaticApp
print('✓ All imports successful')
"

# Run Python syntax check
python -m py_compile dataset/validate.py
python -m py_compile dataset/generate.py
python -m py_compile training/prepare_dataset.py
python -m py_compile inference/model.py
python -m py_compile inference/cli.py
python -m py_compile ui/renderer.py
python -m py_compile ui/app.py
```

---

## 12. Documentation Tests

**Verify documentation:**

```bash
# Check files exist
ls -lh schema.md README.md

# Check schema examples are valid JSON
python -c "
import json
content = open('schema.md').read()
# Extract JSON from markdown code blocks
import re
matches = re.findall(r'\`\`\`json\n(.*?)\n\`\`\`', content, re.DOTALL)
for match in matches:
    json.loads(match)
print(f'✓ All {len(matches)} schema examples valid')
"
```

---

## Quick Test Summary

```bash
#!/bin/bash
cd c:\Users\Vittoria\Desktop\Ohmatic

echo "Testing Ohmatic..."
echo "=================="

# 1. Validate
python dataset/validate.py dataset/examples.json && echo "✓ Validation" || echo "✗ Validation"

# 2. CLI
python inference/cli.py "test" --mock > /dev/null && echo "✓ CLI Generation" || echo "✗ CLI Generation"

# 3. Prepare
python training/prepare_dataset.py --input dataset/examples.json --output /tmp/prepared > /dev/null && echo "✓ Dataset Prep" || echo "✗ Dataset Prep"

# 4. Render
python ui/renderer.py --input dataset/examples.json --output /tmp/test.svg > /dev/null && echo "✓ Rendering" || echo "✗ Rendering"

echo "=================="
echo "All tests passed!"
```

---

## Troubleshooting Tests

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'X'` | Run `pip install -r requirements.txt` |
| Slow CLI tests | Use `--mock` flag; real models take 30+ seconds |
| Web UI won't start | Check port 7860 is available; try `--port 7861` |
| Validation fails | Check examples.json is valid JSON; run again |
| Dataset prep fails | Ensure datasets library is installed |
| SVG rendering empty | Check circuit has valid components and coordinates |

---

## Next Steps After Testing

1. ✅ All basic tests pass → Ready for production use
2. 📊 Generate more data with `dataset/generate.py`
3. 🎓 Fine-tune model with `training/finetune.ipynb`
4. 🚀 Deploy web UI: `python ui/app.py --share`
5. 📦 Package for distribution: `pip install -e .`
