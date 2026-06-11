<p align="center">
  <img src="assets/ohmaticanim.gif" alt="Ohmatic" width="760" />
</p>

<p align="center">
  Describe a circuit in plain language → get a <b>verified</b> schematic, or an honest refusal.<br/>
  Never a broken design.
</p>

---

## How it works

```
user prompt ──► T5 normalizer ──► Qwen3-8B (fine-tuned) ──► ERC verification
                                        ▲                        │
                                        └── self-correction ◄────┘  (up to 3 rounds)
                                                                 │
                                              pass ──► schematic JSON
                                              fail ──► killswitch: ask the user to clarify
```

- **T5 normalizer** maps messy, real-world phrasing onto the model's trained input distribution.
- **The generator** is Qwen3-8B fine-tuned in two self-improvement rounds (the second on its own
  ERC-verified generations — STaR-style), emitting a two-stage circuit JSON (topology + layout).
- **ERC** (electrical rule checker, `eval/diagnostics.py`) validates every candidate: connectivity,
  power integrity, pin legality, structure. On failure the model receives the findings and repairs
  its own design.
- **Killswitch**: if nothing passes after the correction rounds, the user gets a clarification
  request — an unverified circuit is never delivered.

## Quick start

```bash
git clone https://github.com/VittoriaLanzo/Ohmatic.git && cd Ohmatic
ohmatic start            # Windows; `bash ohmatic start` on Linux/macOS
```

Boots the local stack (gateway, service stubs, frontend) and prints a URL. No GPU needed —
the stub inference returns a fixed valid circuit so the whole loop is explorable.

Run the real pipeline (GPU + model weights):

```bash
python -m inference.cli "5V to 3.3V LDO with reverse-polarity protection" \
  --t5-model VittoriaLanzo/ohmatic-t5-normalizer \
  --qwen-model VittoriaLanzo/Ohmatic-Qwen3-8B
```

Model weights (bf16 + GGUF Q8_0/Q4_K_M) live on Hugging Face and are private during evaluation.

## Repo map

| Path | What |
|---|---|
| `inference/` | the production pipeline (T5 → Qwen → ERC → retries → killswitch) + CLI |
| `eval/` | the ERC engine (`diagnostics.py` + `rules/`) and benchmarks |
| `eval/benchmark/cross_model/` | reproducible cross-model benchmark — see its README |
| `shared/` | single sources of truth: system prompt, ERC feedback format, T5 contract |
| `dataset/` | schema, validator, corpus tooling (data itself lives on private HF) |
| `gateway/ frontend/` | local demo stack (`ohmatic start`) |
| `train/` | training scripts (temporary residence — moving to private HF) |

## Tests

```bash
pytest tests/ -q
```

ERC behavior is pinned by a golden regression (`tests/test_erc_golden.py`); the fixture derives
from private held-out data and is built locally — the test skips without it.
