# Architecture

Ohmatic is a five-stage pipeline (Normalize, Generate, Verify, Correct, Refuse), wrapped in a
service layer that runs it locally. One stage is allowed to say no.

<p align="center">
  <img src="../assets/architecture.png" alt="Ohmatic pipeline as a PCB board: Normalize (T5), Generate (Qwen3-8B), Verify (ERC), Deliver (schematic JSON), with an amber self-correction loop from Verify back to Generate and a red killswitch branch that refuses and asks the user to clarify when retries are exhausted" width="900" />
</p>

| Stage | Component | What it does |
|---|---|---|
| Normalize | `shared/t5_normalizer.py` + fine-tuned T5 | maps any phrasing onto the model's trained input distribution; a hard faithfulness gate re-attaches any user-given specifics (voltages, parts) the rewrite dropped |
| Generate | Qwen3-8B fine-tune (`inference/pipeline.py`) | emits a two-stage circuit JSON: `STAGE_1_TOPOLOGY` (components, nets, pins) + `STAGE_2_LAYOUT` (spatial nodes). Trained in two self-improvement rounds: round 1 on a synthetic corpus, round 2 STaR-style on its own ERC-verified generations, each round merge-frozen into the base |
| Verify | `eval/diagnostics.py` + `eval/rules/` | the ERC engine: connectivity, power integrity, pin legality, schema/structure, one source of truth shared by training, the benchmark, and production |
| Correct | the pipeline loop | on ERC failure the model receives the findings (`shared/erc_feedback.py`, the exact format it trained on) and repairs its own design, up to 3 rounds |
| Refuse | the killswitch | retries exhausted, `blocked=True` plus a clarification request; the broken candidate stays internal |
| Serve (service layer) | `gateway/` + `frontend/` | async job API (`POST /v1/generate`, then poll) and the web UI; `ohmatic start` runs it all locally with stubs |

The system prompt the model is served is byte-identical to the one it trained on
(`shared/prompt_builder.py`, single source of truth).
