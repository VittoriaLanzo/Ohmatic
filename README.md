<h1 align="center">Ohmatic</h1>

<p align="center">
  <b>LLMs generate text. Ohmatic compiles circuits.</b><br/>
  A local model drafts the design. A deterministic rule checker decides whether you ever see it.<br/>
  <b>Compiles clean, or it doesn't ship.</b>
</p>

<p align="center">
  <img alt="License: Source-Available" src="https://img.shields.io/badge/license-source--available-2563eb">
  <img alt="Local-first, no telemetry" src="https://img.shields.io/badge/local--first-no%20telemetry-16a34a">
  <a href="https://huggingface.co/VittoriaLanzo"><img alt="Weights on Hugging Face (gated during evaluation)" src="https://img.shields.io/badge/weights-Hugging%20Face%20(gated)-f59e0b"></a>
</p>

<p align="center">
  <img src="assets/ohmaticanim.gif" alt="Ohmatic generating a schematic from a typed prompt and validating it through the rule checker" width="760" />
</p>

---

## Why

Ask a chat model for a circuit and you get one back, working or not, in the same confident tone
either way. Nothing stands between that answer and a broken board. Ohmatic puts a deterministic
verifier in that gap: nothing reaches you until it passes an electrical rule checker. When the
model can't get there, it returns a clarifying question and keeps the broken draft to itself.

<p align="center">
  <img src="assets/benchmark.png" alt="Benchmark across 75 identical prompts judged by the same ERC engine: Ohmatic bf16 93.3% ERC-clean with zero ERC-failing deliveries (the rest withheld by the killswitch); Ohmatic Q4_K_M quant 72.0% ERC-clean, zero ERC-failing; Claude Fable 5 (zero-context, single-shot) 76.0% ERC-clean with 18 of 75 outputs failing the same checks; the untrained Qwen3-8B base 4.0% ERC-clean" width="100%" />
</p>

> Across one 75-prompt run, every circuit Ohmatic delivered passed ERC; the rest were withheld as
> clarification requests. On the identical prompts, zero-context and single-shot, 18 of 75 Claude
> Fable 5 outputs failed the same checks. The full reading is in
> [Benchmark](#benchmark).

## How it works

Five stages. One of them is allowed to say no.

1. **Normalize** rewrites a messy or underspecified prompt onto the input distribution the model trained on, then re-attaches any specifics (voltages, parts) the rewrite dropped.
2. **Generate** emits a two-stage circuit JSON: topology first, then layout.
3. **Verify** runs a deterministic electrical rule checker: connectivity, power integrity, pin legality, structure. The same engine gates training, the benchmark, and production.
4. **Correct** hands the model its own ERC findings, in the exact format it trained on, and lets it repair the design. Up to three rounds.
5. **Refuse** fires the killswitch when the budget runs out: it returns a clarification request, and the candidate that failed ERC stays inside the box.

<p align="center">
  <img src="assets/architecture.png" alt="Ohmatic pipeline as a PCB board: Normalize (T5), Generate (Qwen3-8B), Verify (ERC), Deliver (schematic JSON), with an amber self-correction loop from Verify back to Generate and a red killswitch branch that refuses and asks the user to clarify when retries are exhausted" width="900" />
</p>

Stage-by-stage breakdown, components, and contracts: [docs/architecture.md](docs/architecture.md).

## Benchmark

75 novel "real-user" prompts (messy, underspecified, typo-ridden, authored by a model that is
**not** in the evaluation, overlap-checked against all training data), run end-to-end through the
full product pipeline. "ERC-clean" means a delivered circuit passed the Ohmatic ERC engine:
structurally and electrically consistent against a fixed rule set. Hardware testing and fitness for
a real-world purpose are separate questions (see
[A note on verification](#a-note-on-verification)).

<details>
<summary><b>Methodology and reproduce</b></summary>

Every model is judged by the identical ERC engine on the identical prompts; rates carry Wilson 95%
intervals (bf16 ERC-clean 93.3%, 95% CI 85.3-97.1%; the full set is in the report output).
"Failed ERC" means an output did not pass that engine. Because that engine also trains and gates
Ohmatic, the ERC-clean rate measures conformance to a shared rule set; independent correctness is a
separate question, addressed in [A note on verification](#a-note-on-verification). The comparison is
fair because the rule set is held identical for every model, and Claude Fable 5 received the same
full format specification in its system prompt.

On clean-rate, paired McNemar on the same 75 prompts: Ohmatic-only-clean 17 vs Claude
Fable 5-only-clean 4, exact p = 0.007. Of the 75, Ohmatic delivered 70 (93.3% of all prompts; 100%
of deliveries ERC-clean), withheld 5, and delivered 0 ERC-failing circuits. That zero is structural:
the killswitch withholds anything that fails ERC before it reaches you, and it pays for that in
availability, shown as the withheld column. The same Qwen3-8B base, untrained and single-shot,
reaches 4.0% ERC-clean on these prompts, so on this suite the training accounts for the lift.

Claude Fable 5 was evaluated zero-context: a fresh instance per prompt, no repo or conversation
access, default decoding, single-shot. The ERC self-correction loop is proprietary and a chat user
would not have it. Quantization degrades the generator: the Q4_K_M build still delivers 0
ERC-failing circuits, but its killswitch fires about four times as often (28.0% withheld vs 6.7%),
so the quality loss showed up as extra refusals while every delivery stayed ERC-clean.

```bash
# stage 1: generate (per model leg; append-only, crash-resumable)
python -m eval.benchmark.cross_model.generate --model ohmatic-bf16 --suite realuser
# stage 2: verify every output through the identical extract -> ERC path (free, rerunnable)
python -m eval.benchmark.cross_model.verify
# stage 3: tables (Wilson CI, precision vs availability, per-category)
python -m eval.benchmark.cross_model.report --by-category
```

Hosted legs need `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`; local legs need a GPU and `HF_TOKEN`.
The `realuser` suite is the 75-prompt set the numbers above cite. All pins, the model matrix, and
the fairness contract live in
[`eval/benchmark/cross_model/`](eval/benchmark/cross_model/README.md).
</details>

## Quick start

```bash
git clone https://github.com/VittoriaLanzo/Ohmatic.git && cd Ohmatic
./ohmatic start          # Linux/macOS
.\ohmatic start          # Windows (PowerShell)
```

Boots the local stack (gateway, service stubs, frontend) and prints a URL. No GPU needed: the stub
inference returns a fixed valid circuit so the whole loop is explorable. Stop it with
`./ohmatic stop`.

<details>
<summary><b>Run the real pipeline against local weights (GPU)</b></summary>

The model weights (bf16 + GGUF Q8_0 / Q4_K_M) are gated on Hugging Face during evaluation; the stub
start path above needs none of them. Once you have access, pull them with `./ohmatic fetch`, then:

```bash
python -m inference.cli "5V to 3.3V LDO with reverse-polarity protection" --local
```

Or point at the Hugging Face repos directly:

```bash
python -m inference.cli "5V to 3.3V LDO with reverse-polarity protection" \
  --t5-model VittoriaLanzo/ohmatic-t5-normalizer \
  --qwen-model VittoriaLanzo/Ohmatic-Qwen3-8B
```
</details>

## A note on verification

The automated ERC checks catch structural and electrical rule violations. They are not a
substitute for professional engineering review. Every design should be validated by a qualified
engineer before fabrication or production use. Passing the rule checks shows a circuit is
internally consistent. It does not certify fitness for any particular purpose.

---

<p align="center"><b>Compiles clean, or it doesn't ship.</b></p>

<p align="center"><sub>Claude and Claude Fable 5 are trademarks of Anthropic. Comparisons are nominative, reflect one specific test, and imply no endorsement.</sub></p>
