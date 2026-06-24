# Cross-model benchmark: full reproducibility

Compares a frontier product (OpenAI Codex, run product-vs-product through its own
CLI, no api key) against the end-to-end Ohmatic product (T5 normalizer → Qwen → ERC →
self-correction → **killswitch**) on circuit generation, verified by the same ERC
engine the product ships.

## The three stages

```
stage 1: GENERATE (spends usage, resumable)   stage 2: VERIFY (free, forever)   stage 3: REPORT
python -m eval.benchmark.cross_model.generate  python -m ....verify              python -m ....report
   --model <leg> --suite <suite>                                                   [--by-category]
→ results/{model}.jsonl  (append-only,        → verified/{model}.jsonl          → pass-rate table,
  keyed (suite, prompt_id); reruns skip         same extraction→ERC path          Wilson 95% CI,
  done rows; crashes/rate limits resume         for EVERY model                   precision vs availability,
  without redoing work)                                                           latency, cost
```

## Reproducing every leg

One secret, env only: `HF_TOKEN` (gated weights + the private holdout suites). The
`codex` leg needs NO api key - it drives the local `codex` CLI on the machine's own
subscription. Everything else (model IDs, artifact revisions, decoding, prompt sets)
is pinned in `config.py`.

| Leg | Where it runs | Command |
|---|---|---|
| `codex` | any machine w/ a PLAIN `codex` CLI logged in | `... generate --model codex --suite pcbschemagen` |
| `bf16` | GPU box (2×T4 / A100) | `... generate --model bf16 --suite pcbschemagen` |
| `q4` | GPU box (llama-cpp-python) | `... generate --model q4 --suite pcbschemagen` |
| `q8` | GPU box (llama-cpp-python) | `... generate --model q8 --suite pcbschemagen` |

Codex leg (`codex_cli` adapter): a fresh `codex exec` per ask (`npm i -g @openai/codex`,
logged in - no api key), the Ohmatic spec written to `AGENTS.md` in a sealed temp cwd,
`-s read-only --skip-git-repo-check --ephemeral` for a single-shot zero-context run, at
MAX reasoning effort (`model_reasoning_effort=xhigh`). Codex MUST be PLAIN: a customized
install whose runtime injects extra startup skills/plugins (e.g. a "superpowers" framework)
contaminates every session even with a clean `CODEX_HOME`. Point at an isolated stock
install via env - `OHMATIC_CODEX_BIN` (the binary) + `OHMATIC_CODEX_HOME` (a clean
`CODEX_HOME` holding only `auth.json`) - and verify zero-context with a probe first.

GPU legs: `pip install transformers peft accelerate safetensors sentencepiece
llama-cpp-python`. The Ohmatic legs import `inference.pipeline` (the literal production
code; no benchmark-special path).

## Suites

| Suite | Source | Who runs it |
|---|---|---|
| `forward` | frozen held-out set (HF, private, `data/holdout_v1.jsonl`) | all legs |
| `correction` | held-out ERC-repair cases (HF, private) | **local legs only** (proprietary; enforced in `config.check_suite_allowed`) |
| `pcbschemagen` | PCBBench (PCBSchemaGen v2, MIT), built from source by `make_pcbschemagen_suite.py`, never committed | all legs (the third-party headline suite; see [PCBSCHEMAGEN.md](PCBSCHEMAGEN.md)) |

## Fairness contract (disclosed in any publication)

1. **Byte-identical prompts**: every leg gets the same shared system prompt
   (`shared.prompt_builder.build_system_prompt()`, which doubles as a complete format
   spec for the off-box model) and the same user turns.
2. **Single-shot competitor vs full-pipeline Ohmatic**: Ohmatic legs keep their retry
   loop and killswitch because that IS the product; the off-box leg is pass@1 because
   the ERC feedback format is proprietary. It stays product vs product - the competitor
   runs its shipped product (its own system prompt) with only the Ohmatic format spec
   added, never a bare model behind an api key. The report separates *precision* (of
   delivered circuits, % ERC-clean) from *availability* (% answered) so the killswitch
   trade-off is visible.
3. **One shared lenient extractor** (fences/prose stripped, first balanced JSON object)
   applied to every model equally, then one shared verifier
   (`eval.diagnostics.analyze_schematic`, the single source of truth).
4. **Third-party prompts**: the headline `pcbschemagen` suite is PCBBench (PCBSchemaGen
   v2, MIT) - someone else's prompts, so no leg authored what it is graded on. See
   [PCBSCHEMAGEN.md](PCBSCHEMAGEN.md) for licensing + scope (the single-circuit subset).
5. **Outcome taxonomy**: `delivered_clean` / `delivered_broken` / `blocked_killswitch`
   (Ohmatic refusal, no unverified circuit reaches the user) / `invalid_output`. The
   off-box leg has no killswitch: every ERC failure is a broken circuit delivered.
