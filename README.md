<h1 align="center">Ohmatic</h1>

<p align="center">
  <b>LLMs generate text. Ohmatic compiles circuits.</b><br/>
  A local model drafts the design. A deterministic electrical rule checker decides whether you
  ever see it. Three retries, then it refuses and asks a question. A circuit that fails ERC isn't
  a circuit, it's a bug report.<br/>
  <b>Compiles clean, or it doesn't ship.</b>
</p>

<p align="center">
  <img alt="License: Source-Available" src="https://img.shields.io/badge/license-source--available-2563eb">
  <img alt="Local-first, no telemetry" src="https://img.shields.io/badge/local--first-no%20telemetry-16a34a">
  <a href="https://huggingface.co/VittoriaLanzo"><img alt="Weights on Hugging Face" src="https://img.shields.io/badge/weights-Hugging%20Face-f59e0b"></a>
</p>

<p align="center">
  <img src="assets/ohmaticanim.gif" alt="Ohmatic generating a schematic from a typed prompt and validating it through the rule checker" width="760" />
</p>

---

## Why

Ask a chat model for a circuit and you get one back, working or not. Nothing stands between a
confident-looking answer and a broken board. Ohmatic puts a deterministic verifier in that gap:
every candidate design has to pass an electrical rule checker before it reaches you, and if the
model can't get there within its retry budget, the product refuses and asks you to clarify rather
than handing you a guess.

<p align="center">
  <img src="assets/benchmark.png" alt="Benchmark: Ohmatic bf16 93.3% verified-clean and Ohmatic Q4_K_M quant 72.0% verified-clean, both with zero broken deliveries (killswitch refusals instead) vs Claude Fable 5 76.0% with 24% broken circuits delivered to the user" width="900" />
</p>

> Across a 75-prompt benchmark run end-to-end through the full pipeline, the 8B fine-tune delivered
> **0 broken circuits** (93.3% verified-clean; the rest withheld as clarification requests). Claude
> Fable 5, evaluated on the identical prompts zero-context and single-shot, delivered **18 broken
> circuits (24%)**. Methodology, the full table, and reproduce steps are in
> [Benchmark](#benchmark) below.

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
product refuses and asks for clarification; the unverified candidate is withheld.

## Benchmark

75 novel "real-user" prompts (messy, underspecified, typo-ridden, authored by a model that is
**not** in the evaluation, overlap-checked against all training data), run end-to-end through the
full product pipeline. Verified by the same ERC engine that gates production.

<table>
  <tr>
    <th>model</th><th>N</th><th>delivered clean</th><th>95% CI</th>
    <th>blocked by killswitch</th><th><b>broken circuits delivered</b></th>
  </tr>
  <tr>
    <td><b>Ohmatic bf16</b> (full pipeline, 8B)</td><td>75</td>
    <td><b>93.3%</b></td><td>85.3 - 97.1%</td><td>6.7%</td>
    <td><b>0 (none)</b></td>
  </tr>
  <tr>
    <td>Claude Fable 5 (frontier, single-shot)</td><td>75</td>
    <td>76.0%</td><td>65.2 - 84.2%</td><td>n/a (no killswitch)</td>
    <td><b>18 (24%)</b></td>
  </tr>
  <tr>
    <td><b>Ohmatic Q4_K_M</b> (GGUF quant)</td><td>75</td>
    <td>72.0%</td><td>61.0 - 80.9%</td><td>28.0%</td>
    <td><b>0 (none)</b></td>
  </tr>
</table>

<sub>Wilson 95% intervals; identical prompts, identical verifier for every row. <b>The 8B
fine-tune beats the frontier model it was benchmarked against</b>, paired McNemar on the same 75
prompts: Ohmatic-only-clean 17 vs Fable-only-clean 4, exact p = 0.007, <b>while delivering zero
broken circuits</b>; the frontier model, with no verification loop, handed the user 18.
Quantization degrades the generator (killswitch fires ~4× more); in this run the quality loss
surfaced as more refusals, not broken deliveries. Fable 5 was evaluated
zero-context (fresh instance per prompt, no repo or conversation access, default decoding,
single-shot; the ERC feedback loop is proprietary and end users of a chat model wouldn't have it).</sub>

### Reproduce

```bash
# stage 1: generate (per model leg; append-only, crash-resumable)
python -m eval.benchmark.cross_model.generate --model star-r2-bf16 --suite realuser
# stage 2: verify every output through the identical extract -> ERC path (free, rerunnable)
python -m eval.benchmark.cross_model.verify
# stage 3: tables (Wilson CI, precision vs availability, per-category)
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

Boots the local stack (gateway, service stubs, frontend) and prints a URL. No GPU needed: the
stub inference returns a fixed valid circuit so the whole loop is explorable. `./ohmatic stop`
shuts it down. To pull the published weights first, run `./ohmatic fetch`.

Run the real pipeline against local weights (GPU):

```bash
python -m inference.cli "5V to 3.3V LDO with reverse-polarity protection" --local
```

Or point at the Hugging Face repos directly:

```bash
python -m inference.cli "5V to 3.3V LDO with reverse-polarity protection" \
  --t5-model VittoriaLanzo/ohmatic-t5-normalizer \
  --qwen-model VittoriaLanzo/Ohmatic-Qwen3-8B
```

Model weights (bf16 + GGUF Q8_0 / Q4_K_M) live on Hugging Face, private during evaluation.

## Architecture

| Stage | Component | What it does |
|---|---|---|
| Normalize | `shared/t5_normalizer.py` + fine-tuned T5 | maps any phrasing onto the model's trained input distribution; a hard faithfulness gate re-attaches any user-given specifics (voltages, parts) the rewrite dropped |
| Generate | Qwen3-8B fine-tune (`inference/pipeline.py`) | emits a two-stage circuit JSON: `STAGE_1_TOPOLOGY` (components, nets, pins) + `STAGE_2_LAYOUT` (spatial nodes). Trained in two self-improvement rounds: round 1 on a synthetic corpus, round 2 STaR-style on its own ERC-verified generations, each round merge-frozen into the base |
| Verify | `eval/diagnostics.py` + `eval/rules/` | the ERC engine: connectivity, power integrity, pin legality, schema/structure, one source of truth shared by training, the benchmark, and production |
| Correct | the pipeline loop | on ERC failure the model receives the findings (`shared/erc_feedback.py`, the exact format it trained on) and repairs its own design, up to 3 rounds |
| Refuse | the killswitch | retries exhausted → `blocked=True` + a clarification request; the broken candidate stays internal |
| Serve | `gateway/` + `frontend/` | async job API (`POST /v1/generate` → poll) and the web UI; `ohmatic start` runs it all locally with stubs |

The system prompt the model is served is byte-identical to the one it trained on
(`shared/prompt_builder.py`, single source of truth).

## Tests

```bash
pytest tests/ -q
```

ERC behavior is pinned by a 182-circuit golden regression (`tests/test_erc_golden.py`); the fixture
derives from private held-out data and is built locally, so the test skips without it.

## A note on verification

The automated ERC checks catch structural and electrical rule violations. They are not a
substitute for professional engineering review. Every design should be validated by a qualified
engineer before fabrication or production use. Passing the rule checks means a circuit is
internally consistent, not that it is fit for any particular purpose.
