# `pcbschemagen` suite — third-party external-validity probe

A neutral, **third-party** benchmark leg: someone else's prompts, **our** ERC. It exists to
defeat the two circularity attacks on a self-built benchmark — *"you wrote the prompts"* and
*"you graded with your own ruler"* — by sourcing the tasks from an independent, permissively
licensed corpus and (optionally) corroborating outcomes against that corpus's own verifier.

## Source & licensing

- **PCBSchemaGen v2** — <https://github.com/HZou9/PCBSchemaGen_v2>, **MIT** (© 2026
  Huanghaohe Zou, Peng Han, Emad Nazerian, Mafu Zhang, Zhicheng Guo, Alex Q. Huang).
- We use **only `benchmarks/pcbbench/benchmark.tsv`** — the 62 *single-circuit* tasks, which
  match Ohmatic's per-request granularity. The 165-task Open-Schematics-Eval set is
  *board-level* (median ~8, up to 28 component types) and is **excluded**: Ohmatic builds one
  focused circuit per request, not whole multi-IC boards, so OSE would measure a granularity
  mismatch, not circuit quality.
- MIT obligation: if the materialised suite is ever redistributed, ship their `LICENSE` +
  copyright notice with it and cite their paper. `make_pcbschemagen_suite.py` keeps that
  provenance in-tree so the obligation can't be lost.

## Why our ERC, not theirs

PCBSchemaGen's verifier scores **spec-completion + topology** (did you build the required
parts, validly connected) and rewards matching the *exact* required part (AMC1350, OPA328…).
Our ERC scores **electrical soundness** (power nets, current limiting, decoupling, polarity…).
They are *complementary axes*, not substitutes — and their exact-part reward would penalise
Ohmatic for legitimately substituting from its family catalog. So we run **their prompts
through our ERC**. Using their verifier as an *independent corroboration* layer (re-scoring
the same outputs) is a separate, future step — corroboration, never replacement.

## Conditions (fairness)

| Cond. | What the competitor is given | Meaning |
|------|------------------------------|---------|
| **C1** | JSON schema + component registry, **no ERC rules** | "level the field" — the format so it *can* emit the schema, but not Ohmatic's rule-set moat. This is the product-vs-product read. |
| **C2** | schema + registry **+ ERC rules** | the backstop — even handed the rules (and, for a real test, retries against them), does a rules-blind frontier model match a verifier-gated system? |

Toggle with `OHMATIC_C1_NO_ERC_RULES=1` (strips the `=== ERC RULES ===` section from the
shared system prompt for the off-box legs; Ohmatic legs build their own prompt internally so
they are unaffected). Ohmatic always runs its full pipeline incl. the killswitch.

## Legs

- **Ohmatic (ours):** `q4` (Q4_K_M, ~4.7 GB), `q8` (Q8_0, ~8.5 GB),
  `bf16` (~16 GB — needs 2×T4 or A100). Full pipeline: T5 normalize → Qwen → ERC →
  retries → **killswitch** (abstains rather than ship an ERC-failing circuit).
- **Competitor:** `codex` (OpenAI Codex, xhigh effort) — a fresh, zero-context, single-shot
  product instance via its CLI, given the C1/C2 system prompt.

## Run it

```bash
# 1. build the suite from source (reproducible; downloads PCBBench from GitHub)
python -m eval.benchmark.cross_model.make_pcbschemagen_suite

# 2a. an Ohmatic leg (GPU) — locally or via the Kaggle runner
python -m eval.benchmark.cross_model.generate --model q4 --suite pcbschemagen

# 2b. a competitor leg, C1 (no ERC rules), single-shot product CLI
OHMATIC_C1_NO_ERC_RULES=1 \
  python -m eval.benchmark.cross_model.generate --model codex --suite pcbschemagen

# 3. verify (free, deterministic ERC) + report
python -m eval.benchmark.cross_model.verify
python -m eval.benchmark.cross_model.report --suite pcbschemagen --by-category
```

### On Kaggle (the GPU legs)

`kaggle/run_pcbschemagen.py` is parametric over the three Ohmatic legs. Per leg, inject the env
into a launch-only copy of the runner (never commit the token) and push the kernel:

- `OHMATIC_BENCH_MODEL` = `q4` | `q8` | `bf16`
- `HF_TOKEN` — private weights; env-injected at launch, or a Kaggle Secret named `HF_TOKEN`.
- **code delivery:** the runner clones GitHub `main` for the pipeline, then either checks out a
  pushed branch (`OHMATIC_BENCH_REF=<branch>`) **or** overlays the bench `.py` files from a mounted
  dataset (`OHMATIC_BENCH_CODE=/kaggle/input/<dataset>`) — the latter lets an *unpushed* branch run.
- `OHMATIC_BENCH_N` — optional cap (default 0 = all 62).

**GPU:** q4 (~4.7 GB) and q8 (~8.5 GB) fit one T4. **bf16 (~16 GB) needs a 2×T4 kernel** — the hf
backend loads with `device_map="auto"` and shards across both GPUs; a single 15 GB T4 OOMs.

The leg runs the shipped public pipeline; its T5 front-end is the live **public V2**
(`VittoriaLanzo/ohmatic-t5-normalizer`). Raw generations and verified outcomes are saved to
`/kaggle/working/<model>.results.jsonl` and `<model>.verified.jsonl` (distinct names, both preserved).

## What the report shows

Axes are kept **separate** (never fold JSON-format failures into "broken"):
`json%` (valid schema) · `erc-clean%` (+Wilson CI) · `graded` (severity-weighted partial
credit) · `broken%` (ERC-failing *deliveries*; rule-of-three upper bound when 0) · `block%`
(killswitch abstentions) · `avail%` (coverage) · `prec%` (clean / delivered) · **`AUGRC`**
(area under the generalized risk-coverage curve — the average risk of *undetected* failures,
the metric the killswitch minimises). Plus per-model ERC-code histograms and paired McNemar.

## Results (PCBBench-62, condition C1)

Identical prompts and identical ERC for every leg. The headline is the *failure mode*, not the
clean rate:

| leg | ERC-clean | abstained (killswitch) | broken delivered |
|-----|-----------|------------------------|------------------|
| Ohmatic q4 (Q4_K_M) | 30/62 (48%) | 32/62 | **0** (rule-of-three ≤ 4.8%) |
| Ohmatic q8 (Q8_0)   | 28/62 (45%) | 34/62 | **0** (≤ 4.8%) |
| Ohmatic bf16        | 27/62 (44%) | 35/62 | **0** (≤ 4.8%) |
| Codex (C1)          | 40/62 (65%) | 0      | **22/62 (35%)** |

Same ballpark clean rate, opposite failure mode: every Ohmatic precision (q4 → q8 → bf16) abstains
rather than ship an ERC-failing circuit (**0 broken delivered**, AUGRC 0.000), while the frontier
competitor delivers 22 broken circuits (AUGRC 0.066). bf16 is marginally *more* conservative than
the quantized legs (it abstains slightly more), so the killswitch guarantee is a property of the
pipeline, not an artifact of quantization.

**Scope caveat.** Ohmatic is trained to circuits of **≤30 components**; PCBBench spans circuits up
to **50**. The largest tasks are therefore out-of-distribution for Ohmatic — it cannot build them
and (correctly) abstains rather than guess, so a non-trivial share of its abstentions are a
training-scope limit, not just killswitch caution. Its clean rate here is, to that extent,
conservative: on the subset it was trained to cover the coverage is higher.
