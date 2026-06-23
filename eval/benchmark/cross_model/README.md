# Cross-model benchmark: full reproducibility

Compares frontier chat models - run product-vs-product through their own CLIs, no
api key - against the end-to-end Ohmatic product (T5 normalizer → Qwen → ERC →
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

One secret, env only: `HF_TOKEN` (the private holdout suites). The Claude legs
(`fable-5`, `opus`) and the `codex` leg need NO api key - they drive the local
`claude` / `codex` CLI on the machine's own subscription. Everything else (model
IDs, artifact revisions, decoding, prompt sets) is pinned in `config.py`.

| Leg | Where it runs | Command |
|---|---|---|
| `fable-5` | any machine w/ the `claude` CLI logged in | `... generate --model fable-5 --suite realuser` |
| `opus` | any machine w/ the `claude` CLI logged in | `... generate --model opus --suite realuser` |
| `codex` | any machine w/ a PLAIN `codex` CLI logged in | `... generate --model codex --suite realuser` |
| `bf16` | GPU box | `... generate --model bf16 --suite forward` |
| `q4` | GPU box (llama-cpp-python) | `... generate --model q4 --suite forward` |
| `noT5` | GPU box (ablation) | `... generate --model noT5 --suite realuser` |
| `qwen3-base` | GPU box (A40+) | `... generate --model qwen3-base --suite forward` |
| `qwen3-base-1shot` | A40+ or 2x T4 | `... generate --model qwen3-base-1shot --suite realuser` |

Claude legs (`claude_cli` adapter): every ask spins up a fresh `claude -p` instance
(`npm i -g @anthropic-ai/claude-code`, logged in - no api key). The Ohmatic format
spec rides on top of Claude's own product prompt via `--append-system-prompt-file`;
the run cwd is a throwaway temp dir SEALED as its own git repo so no project
CLAUDE.md / memory / git context is inherited (verified zero-context, identical on
every machine). `--allowed-tools none` keeps it single-shot. This is product vs
product: the shipped Claude product, not a bare model behind an api key.

Codex leg (`codex_cli` adapter): the OpenAI mirror - a fresh `codex exec` per ask
(`npm i -g @openai/codex`, logged in - no api key), the Ohmatic spec written to
`AGENTS.md` in the same sealed temp cwd, `-s read-only --skip-git-repo-check
--ephemeral` for a single-shot zero-context run, at MAX reasoning effort
(`model_reasoning_effort=xhigh`). Codex MUST be PLAIN: a customized install whose
runtime injects extra startup skills/plugins (e.g. a "superpowers" framework)
contaminates every session even with a clean `CODEX_HOME`. Point at an isolated
stock install via env - `OHMATIC_CODEX_BIN` (the binary) + `OHMATIC_CODEX_HOME`
(a clean `CODEX_HOME` holding only `auth.json`) - and verify zero-context with a
probe before trusting the leg.

GPU legs: `pip install transformers peft accelerate safetensors sentencepiece
llama-cpp-python`. The Ohmatic legs import `inference.pipeline` (the literal
production code; no benchmark-special path).

The single-shot base leg (`qwen3-base-1shot`) needs vLLM instead: `pip install
vllm==0.9.2 transformers==4.51.3`. That transformers window is required (5.x breaks
vLLM 0.9.2's config import; >=4.54 collides on the `aimv2` config name). It runs the
base model pass@1 through vLLM in fp16 (Turing GPUs have no bf16), tensor-parallel
auto-scaled to the visible GPUs, with no T5/ERC/killswitch: the base-vs-trained
control that isolates the lift as training, not the 8B base.

## Suites

| Suite | Source | Who runs it |
|---|---|---|
| `forward` | frozen held-out set (HF, private, `data/holdout_v1.jsonl`) | all legs |
| `realuser` | `data/realuser_prompts.jsonl`, 75 novel messy prompts | all legs |
| `correction` | held-out ERC-repair cases (HF, private) | **local legs only** (proprietary; enforced in `config.check_suite_allowed`) |
| `pcbschemagen` | PCBBench (PCBSchemaGen v2, MIT), built from source by `make_pcbschemagen_suite.py`, never committed | all legs &mdash; the third-party headline suite; see [PCBSCHEMAGEN.md](PCBSCHEMAGEN.md) |

## Fairness contract (disclosed in any publication)

1. **Byte-identical prompts**: every leg gets the same shared system prompt
   (`shared.prompt_builder.build_system_prompt()`, the spec the fine-tunes
   trained on, which doubles as a complete format spec for frontier models)
   and the same user turns.
2. **Single-shot Claude product vs full-pipeline Ohmatic**: Ohmatic legs keep
   their retry loop and killswitch because that IS the product; the Claude legs
   are pass@1 because the ERC feedback format is proprietary. It stays product
   vs product - the Claude legs run the shipped Claude product (its own system
   prompt) with only the Ohmatic format spec added, never a bare model behind an
   api key. The report separates *precision* (of delivered circuits, % ERC-clean)
   from *availability* (% answered) so the killswitch trade-off is visible.
3. **One shared lenient extractor** (fences/prose stripped, first balanced
   JSON object) applied to every model equally, then one shared verifier
   (`eval.diagnostics.analyze_schematic`, the single source of truth).
4. **Prompt authorship (with disclosure)**: the `realuser` suite was authored by
   Claude Opus, blinded from the training data and overlap-checked against the
   holdout + training corpus (max Jaccard 0.30, flag line 0.60). Opus is now also
   an evaluated leg, so on `realuser` it answers prompts it wrote - a home-field
   advantage that biases IN FAVOUR of the Claude side, making any Ohmatic win
   there conservative. The held-out `forward` suite (not Opus-authored) is the
   contamination-free cross-check.
5. **Outcome taxonomy**: `delivered_clean` / `delivered_broken` /
   `blocked_killswitch` (Ohmatic refusal, no unverified circuit reaches the
   user) / `invalid_output`. The off-box legs have no killswitch: every ERC failure
   is a broken circuit delivered to the user.
