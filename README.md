<p align="center">
  <img src="assets/ohmaticanim.gif" alt="Ohmatic" width="760" />
</p>

<p align="center">
  Describe a circuit in plain language → get a <b>verified</b> schematic, or an honest refusal.<br/>
  <b>Never a broken design.</b>
</p>

---

## How it works

```
user prompt ──► T5 normalizer ──► Qwen3-8B (fine-tuned) ──► ERC verification
                                        ▲                        │
                                        └── self-correction ◄────┘  (up to 3 rounds)
                                                                 │
                                              pass ──► schematic JSON (topology + layout)
                                              fail ──► killswitch: ask the user to clarify
```

Every candidate design is validated by a deterministic **electrical rule checker** before it can
reach the user. If the model can't produce a passing design within its correction budget, the
product refuses and asks for clarification — an unverified circuit is never delivered.

## Benchmark

75 novel "real-user" prompts (messy, underspecified, typo-ridden — authored by a model that is
**not** in the evaluation, overlap-checked against all training data), run end-to-end through the
full product pipeline. Verified by the same ERC engine that gates production.

<p align="center">
  <img src="assets/benchmark.png" alt="Benchmark: Ohmatic bf16 93.3% verified-clean and Ohmatic Q4_K_M quant 73.5% verified-clean, both with zero broken deliveries (killswitch refusals instead) vs Claude Fable 5 76.0% with 24% broken circuits delivered to the user" width="900" />
</p>

<table>
  <tr>
    <th>model</th><th>N</th><th>delivered clean</th><th>95% CI</th>
    <th>blocked by killswitch</th><th><b>broken circuits delivered</b></th><th>latency</th>
  </tr>
  <tr>
    <td><b>Ohmatic bf16</b> (full pipeline, 8B)</td><td>75</td>
    <td><b>93.3%</b></td><td>85.3 – 97.1%</td><td>6.7%</td>
    <td><b>0 — none</b></td><td>122 s</td>
  </tr>
  <tr>
    <td>Claude Fable 5 (frontier, single-shot)</td><td>75</td>
    <td>76.0%</td><td>65.2 – 84.2%</td><td>— (no killswitch)</td>
    <td><b>18 (24%)</b></td><td>~40 s</td>
  </tr>
  <tr>
    <td><b>Ohmatic Q4_K_M</b> (GGUF quant)</td><td>34</td>
    <td>73.5%</td><td>56.9 – 85.4%</td><td>26.5%</td>
    <td><b>0 — none</b></td><td>40 s</td>
  </tr>
</table>

<sub>Wilson 95% intervals; identical prompts, identical verifier for every row. <b>The 8B
fine-tune beats the frontier model it was benchmarked against</b> — paired McNemar on the same 75
prompts: Ohmatic-only-clean 17 vs Fable-only-clean 4, exact p = 0.007 — <b>while delivering zero
broken circuits</b>; the frontier model, with no verification loop, handed the user 18.
Quantization degrades the generator (killswitch fires 4× more) but still ships nothing broken:
quality loss converts to reduced availability, never to bad output. Fable 5 was evaluated
zero-context (fresh instance per prompt, no repo or conversation access, default decoding,
single-shot — the ERC feedback loop is proprietary and end users of a chat model wouldn't have it).
OpenAI-model leg pending.</sub>

### Reproduce

```bash
# stage 1 — generate (per model leg; append-only, crash-resumable)
python -m eval.benchmark.cross_model.generate --model star-r2-bf16 --suite realuser
# stage 2 — verify: every output through the identical extract → ERC path (free, rerunnable)
python -m eval.benchmark.cross_model.verify
# stage 3 — tables (Wilson CI, precision vs availability, per-category)
python -m eval.benchmark.cross_model.report --by-category
```

Hosted legs need `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`; local legs need a GPU and `HF_TOKEN`.
All pins, the model matrix, and the fairness contract live in
[`eval/benchmark/cross_model/`](eval/benchmark/cross_model/README.md).

## Quick start

```bash
git clone https://github.com/VittoriaLanzo/Ohmatic.git && cd Ohmatic
ohmatic start            # Windows; `bash ohmatic start` on Linux/macOS
```

Boots the local stack — gateway, service stubs, frontend — and prints a URL. No GPU needed: the
stub inference returns a fixed valid circuit so the whole loop is explorable. `./ohmatic stop`
shuts it down.

Run the real pipeline (GPU + model weights):

```bash
python -m inference.cli "5V to 3.3V LDO with reverse-polarity protection" \
  --t5-model VittoriaLanzo/ohmatic-t5-normalizer \
  --qwen-model VittoriaLanzo/Ohmatic-Qwen3-8B
```

Model weights (bf16 + GGUF Q8_0 / Q4_K_M) live on Hugging Face — private during evaluation.

## Architecture

| Stage | Component | What it does |
|---|---|---|
| Normalize | `shared/t5_normalizer.py` + fine-tuned T5 | maps any phrasing onto the model's trained input distribution; a hard faithfulness gate re-attaches any user-given specifics (voltages, parts) the rewrite dropped |
| Generate | Qwen3-8B fine-tune (`inference/pipeline.py`) | emits a two-stage circuit JSON — `STAGE_1_TOPOLOGY` (components, nets, pins) + `STAGE_2_LAYOUT` (spatial nodes). Trained in two self-improvement rounds: round 1 on a synthetic corpus, round 2 STaR-style on its own ERC-verified generations, each round merge-frozen into the base |
| Verify | `eval/diagnostics.py` + `eval/rules/` | the ERC engine: connectivity, power integrity, pin legality, schema/structure — one source of truth shared by training, the benchmark, and production |
| Correct | the pipeline loop | on ERC failure the model receives the findings (`shared/erc_feedback.py`, the exact format it trained on) and repairs its own design, up to 3 rounds |
| Refuse | the killswitch | retries exhausted → `blocked=True` + a clarification request; the broken candidate stays internal |
| Serve | `gateway/` + `frontend/` | async job API (`POST /v1/generate` → poll) and the web UI; `ohmatic start` runs it all locally with stubs |

The system prompt the model is served is byte-identical to the one it trained on
(`shared/prompt_builder.py` — single source of truth).

## Tests

```bash
pytest tests/ -q
```

ERC behavior is pinned by a 182-circuit golden regression (`tests/test_erc_golden.py`); the fixture
derives from private held-out data and is built locally — the test skips without it.
