# Cross-model benchmark: full reproducibility

Compares hosted frontier models against the end-to-end Ohmatic product
(T5 normalizer → Qwen → ERC → self-correction → **killswitch**) on circuit
generation, verified by the same ERC engine the product ships.

## The three stages

```
stage 1: GENERATE (costs money, resumable)   stage 2: VERIFY (free, forever)   stage 3: REPORT
python -m eval.benchmark.cross_model.generate  python -m ....verify              python -m ....report
   --model <leg> --suite <suite>                                                   [--by-category]
→ results/{model}.jsonl  (append-only,        → verified/{model}.jsonl          → pass-rate table,
  keyed (suite, prompt_id); reruns skip         same extraction→ERC path          Wilson 95% CI,
  done rows; crashes/rate limits resume         for EVERY model                   precision vs availability,
  without double-paying)                                                          latency, cost
```

## Reproducing every leg

Secrets via env only: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (+`OPENAI_MODEL`,
optional `OPENAI_BASE_URL`), `HF_TOKEN`. Everything else (model IDs, artifact
revisions, decoding, prompt sets) is pinned in `config.py`.

| Leg | Where it runs | Command |
|---|---|---|
| `fable-5` | any machine w/ Anthropic key | `... generate --model fable-5 --suite forward` |
| `codex-5.5` | any machine w/ OpenAI key | `... generate --model codex-5.5 --suite forward` |
| `qwen3-base` | GPU box (A40+) | `... generate --model qwen3-base --suite forward` |
| `star-r2-bf16` | GPU box | `... generate --model star-r2-bf16 --suite forward` |
| `star-r2-q4` | GPU box (llama-cpp-python) | `... generate --model star-r2-q4 --suite forward` |
| `star-r2-noT5` | GPU box (ablation) | `... generate --model star-r2-noT5 --suite realuser` |

GPU legs: `pip install transformers peft accelerate safetensors sentencepiece
llama-cpp-python`. The Ohmatic legs import `inference.pipeline` (the literal
production code; no benchmark-special path).

## Suites

| Suite | Source | Who runs it |
|---|---|---|
| `forward` | frozen held-out set (HF, private, `data/holdout_v1.jsonl`) | all legs |
| `realuser` | `data/realuser_prompts.jsonl`, 75 novel messy prompts | all legs |
| `correction` | held-out ERC-repair cases (HF, private) | **local legs only** (proprietary; enforced in `config.check_suite_allowed`) |

## Fairness contract (disclosed in any publication)

1. **Byte-identical prompts**: every leg gets the same shared system prompt
   (`shared.prompt_builder.build_system_prompt()`, the spec the fine-tunes
   trained on, which doubles as a complete format spec for frontier models)
   and the same user turns.
2. **Single-shot hosted vs full-pipeline local**: Ohmatic legs keep their
   retry loop and killswitch because that IS the product; hosted legs are
   pass@1 because the ERC feedback format is proprietary. The report separates
   *precision* (of delivered circuits, % ERC-clean) from *availability*
   (% of requests answered) so the killswitch trade-off is visible, not hidden.
3. **One shared lenient extractor** (fences/prose stripped, first balanced
   JSON object) applied to every model equally, then one shared verifier
   (`eval.diagnostics.analyze_schematic`, the single source of truth).
4. **Neutral prompt authorship**: the `realuser` suite was authored by a model
   that is not in the matrix (Claude Opus), blinded from the training data,
   and overlap-checked against the holdout + training corpus (max Jaccard
   0.30, flag line 0.60).
5. **Outcome taxonomy**: `delivered_clean` / `delivered_broken` /
   `blocked_killswitch` (Ohmatic refusal, no unverified circuit reaches the
   user) / `invalid_output`. Hosted legs have no killswitch: every ERC failure
   is a broken circuit delivered to the user.
