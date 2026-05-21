# Ohmatic: AI-Powered Circuit Schematic Generator

Generate valid electronic circuit schematics using AI. Runs fully locally on low-end hardware (CPU-only, 8GB RAM minimum) with no cloud dependencies.

## Features

- 🧠 **Fine-tuned LLM**: Qwen2.5-3B optimized for circuit generation (QLoRA)
- 🚀 **Local Inference**: llama-cpp-python for efficient CPU inference
- ✅ **Schema Validation**: Built-in validation against v0.1 schema
- 🎨 **SVG Rendering**: Automatic schematic visualization
- 🌐 **Web UI**: Gradio interface for easy generation
- 📊 **Batch Generation**: Scale up dataset using Claude API
- 🔧 **Extensible**: Easy to add new component types

## Stack

- **Python 3.11**
- **llama-cpp-python** - Local inference
- **Unsloth + QLoRA** - Fine-tuning
- **Gradio** - Web UI
- **Pydantic** - Data validation
- **HuggingFace Datasets** - Dataset management

## Installation

```bash
# Clone and setup
git clone https://github.com/...
cd ohmatic
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Optional: CUDA Support

For GPU acceleration:
```bash
pip install llama-cpp-python[gpu] --no-cache-dir
```

## Quick Start

### 1. Generate Circuits from CLI

```bash
# Using mock model (no GGUF needed for testing)
python inference/cli.py "LED circuit with resistor" --mock

# With real model (requires GGUF file)
python inference/cli.py "555 timer oscillator" --model model.gguf --temperature 0.7
```

### 2. Launch Web UI

```bash
python ui/app.py --share
# Opens at http://localhost:7860
```

### 3. Validate Circuits

```bash
python dataset/validate.py dataset/examples.json
# Output: Validation: 20/20 circuits valid
```

### 4. Generate Dataset

```bash
# Generate more examples using Claude API
python dataset/generate.py --api-key sk-... --num-circuits 10 --append

# Output: Total circuits: 30
```

## Project Structure

```
ohmatic/
├── README.md              # This file
├── schema.md              # Circuit schema v0.1 specification
├── requirements.txt       # Dependencies
│
├── dataset/
│   ├── examples.json      # 20 seed circuit examples
│   ├── validate.py        # Schema validator
│   ├── generate.py        # Batch generation via API
│   └── prepared/          # Generated train/test splits
│
├── training/
│   ├── prepare_dataset.py # Convert JSON → HuggingFace format
│   └── finetune.ipynb     # QLoRA fine-tuning notebook (Colab)
│
├── inference/
│   ├── model.py           # llama-cpp-python wrapper
│   └── cli.py             # Command-line interface
│
└── ui/
    ├── app.py             # Gradio web application
    └── renderer.py        # JSON → SVG converter
```

## Usage Guide

### Validating Circuits

```python
from dataset.validate import SchemaValidator

validator = SchemaValidator()
is_valid = validator.validate_circuit(circuit_dict)
if not is_valid:
    for error in validator.get_errors():
        print(f"  - {error}")
```

### Generating Circuits Programmatically

```python
from inference.model import load_model

model = load_model("model.gguf")
circuit = model.generate_circuit("OpAmp inverting amplifier")
print(circuit)  # Parsed circuit dict
```

### Rendering to SVG

```python
from ui.renderer import SchematicRenderer
import json

renderer = SchematicRenderer()

with open("dataset/examples.json") as f:
    circuits = json.load(f)

renderer.render_to_file(circuits[0], Path("circuit.svg"))
```

## Training

### Prepare Dataset

```bash
python training/prepare_dataset.py \
    --input dataset/examples.json \
    --output dataset/prepared \
    --test-split 0.1
```

Creates:
- `dataset/prepared/train.parquet` (90% of data)
- `dataset/prepared/test.parquet` (10% of data)
- `dataset/prepared/huggingface/` (HuggingFace format)

### Fine-tune Model

Use the provided Colab notebook:

1. Open [finetune.ipynb](training/finetune.ipynb)
2. Adjust hyperparameters
3. Run cells to fine-tune Qwen2.5-3B with QLoRA
4. Download GGUF model to `model.gguf`

**Colab settings:**
- GPU: T4 (free tier)
- Runtime: 8-12 hours
- VRAM: ~15GB (fits T4)

## Circuit Schema (v0.1)

See [schema.md](schema.md) for full specification.

### Structure

```json
{
  "metadata": {
    "title": "Circuit name",
    "description": "Description",
    "version": "0.1",
    "tags": ["tag1", "tag2"]
  },
  "components": [
    {
      "id": "R1",
      "type": "resistor",
      "part": "1/4W",
      "value": "10kΩ",
      "pins": {"1": "1", "2": "2"},
      "x": 50,
      "y": 50
    }
  ],
  "nets": [
    {"name": "VCC", "pins": ["VCC1.1", "R1.1"]},
    {"name": "GND", "pins": ["R1.2", "GND1.1"]}
  ]
}
```

### Validation

Every circuit must:
- Have unique component IDs
- Use valid component types
- Connect every pin to exactly one net
- Include VCC and GND nets
- Have at least 2 pins per net

## Batch Generation

Generate more training data using Claude API:

```bash
python dataset/generate.py \
    --api-key sk-ant-... \
    --num-circuits 20 \
    --append \
    --model claude-3-5-sonnet-20241022
```

This:
1. Generates 20 circuit descriptions
2. Validates each one
3. Appends valid circuits to examples.json

**Cost:** ~$0.05 per 10 circuits (Claude 3.5 Sonnet pricing)

## Performance

### Inference Speed (local, CPU)

| Hardware | Model Size | Inference Time |
|----------|-----------|-----------------|
| 8GB RAM CPU (i5) | 3B | 30-60 seconds |
| 16GB RAM CPU (Ryzen) | 3B | 15-30 seconds |
| GPU (T4) | 3B | 2-5 seconds |
| GPU (A100) | 3B | <1 second |

### File Sizes

- Model (Q4 quantized): ~2.5 GB
- Examples dataset: ~500 KB
- Prepared dataset: ~5 MB

## Examples

### LED Circuit
```
Input: "Simple LED circuit with 330 ohm resistor"
Output: Valid circuit with VCC → R1 → LED1 → GND
```

### 555 Timer
```
Input: "Astable 555 timer oscillator at 1 kHz"
Output: Valid circuit with timing capacitors and resistors
```

### OpAmp Amplifier
```
Input: "Non-inverting amplifier with gain of 10"
Output: Valid circuit with feedback resistors and bypass caps
```

## API Reference

### CLI

```bash
# Generate circuit
python inference/cli.py "<description>" [--model MODEL] [--temperature 0-1] [--mock]

# Validate
python dataset/validate.py examples.json

# Prepare training data
python training/prepare_dataset.py [--input FILE] [--output DIR]

# Generate batch
python dataset/generate.py --api-key KEY [--num-circuits N]

# Render to SVG
python ui/renderer.py [--input INPUT] [--output OUTPUT] [--circuit INDEX]

# Web UI
python ui/app.py [--model MODEL] [--share] [--port PORT]
```

### Python API

```python
# Validation
from dataset.validate import SchemaValidator
validator = SchemaValidator()
is_valid = validator.validate_circuit(circuit)

# Inference
from inference.model import load_model
model = load_model("model.gguf")
circuit = model.generate_circuit("description")

# Rendering
from ui.renderer import SchematicRenderer
renderer = SchematicRenderer()
svg = renderer.render(circuit)

# Batch generation
from dataset.generate import CircuitGenerator
gen = CircuitGenerator(api_key="sk-...")
circuits = gen.generate_batch(["prompt1", "prompt2"])
```

## Troubleshooting

### "Model not found"
- Place GGUF file in project root: `model.gguf`
- Or use `--mock` for testing

### Out of memory
- Reduce context window: `-n_ctx 1024`
- Use quantized model (Q4 or Q5)
- Reduce batch size in training

### Slow inference
- Check GPU availability: `--model model.Q5_K_M.gguf`
- Install CUDA support
- Pre-load model once

### Invalid JSON generated
- Lower temperature (more deterministic)
- Add more training examples
- Fine-tune longer

## Contributing

Contributions welcome! Areas for help:

- [ ] Add more seed examples
- [ ] Optimize SVG renderer
- [ ] Support more component types
- [ ] Improve grammar constraints
- [ ] Create component symbol library

## License

MIT

## Citation

```bibtex
@software{ohmatic,
  title={Ohmatic: AI-Powered Circuit Schematic Generator},
  author={Your Name},
  year={2025},
  url={https://github.com/...}
}
```

## Resources

- [Qwen2.5-3B on HuggingFace](https://huggingface.co/Qwen/Qwen2.5-3B)
- [llama-cpp-python](https://github.com/abetlen/llama-cpp-python)
- [Unsloth QLoRA](https://github.com/unslothai/unsloth)
- [Gradio Docs](https://www.gradio.app/)
- [Circuit Schema](schema.md)

## FAQ

**Q: Can I use a different LLM?**
A: Yes! Change the model in training or use quantized versions of Mistral, Llama, etc.

**Q: How many circuits do I need to fine-tune?**
A: 20-30 examples work well. More = better, but follow diminishing returns.

**Q: Can I run this on my laptop?**
A: Yes! CPU inference works fine. Inference takes 30-60 seconds per circuit on 8GB CPU.

**Q: How do I export the circuit?**
A: Use the renderer to SVG, then open in any vector editor (Inkscape, Adobe Illustrator).

**Q: Can I train on my GPU?**
A: Yes! Use the Colab notebook or modify `finetune.ipynb` for your local GPU.

## Support

- 📖 [Documentation](schema.md)
- 🐛 [Issues](https://github.com/.../issues)
- 💬 [Discussions](https://github.com/.../discussions)
