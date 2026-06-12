# Ohmatic held-out benchmark

A **frozen**, never-trained-on evaluation set for honest, reproducible quality numbers
(ERC pass-rate, generalization, grokking). The benchmark *data* lives on the private HF
dataset repo (it is derived from the private dataset and is gitignored here); only the
scripts in this directory are public.

## Why two partitions

| Partition | What it is | Claim it supports |
|---|---|---|
| `unseen_variant` | Unseen specs from families the model **did** train on | "X% ERC pass on unseen circuit specifications" |
| `novel_family` | **Entire** circuit families removed from training | The grokking proof: "valid circuits for topologies never seen" |

## Metrics

- **parse_rate**: output parses as a JSON object
- **erc_pass_rate**: parses **and** passes the Ohmatic ERC engine (overall + per partition)
- **generalization_gap**: trained-prompt ERC pass-rate minus held-out pass-rate (small = generalized)
- **loopback_repair_rate**: given a broken circuit + ERC errors, does the fix pass ERC?
- **grokking signature**: did held-out ERC pass-rate keep rising *after* train loss plateaued?

## Workflow

```bash
# 1. Freeze the benchmark + the train-exclusion lists (run once per dataset release)
python eval/benchmark/build_holdout.py            # writes holdout_*.{jsonl,txt}, manifest
python eval/benchmark/build_holdout.py --verify-only   # re-check integrity any time

# 2. Push the benchmark to HF private (the pod pulls the exclude files from here)
python eval/benchmark/upload_holdout_to_hf.py

# 3. Train: finetune_runpod.py pulls the exclude files and HARD-FAILS if absent,
#    so the model can never train on benchmark prompts (zero contamination, by design).

# 4. After training, on the pod (GPU): base vs fine-tune on the frozen set
python eval/benchmark/verify_model.py \
    --adapter /workspace/ohmatic-checkpoints/best-erc-adapter

# 5. Quantify the grokking transition from the wandb run history (runs anywhere)
python eval/benchmark/grokking_signature.py --run VittoriaLanzo/ohmatic-qwen3/<run_id>
#   (matplotlib optional; without it you still get the CSV + JSON + markdown)
```

## Integrity guarantees

- Every reference circuit in the benchmark **passes ERC** (clean ground truth), enforced at build time.
- Every benchmark prompt hash is in the exclude list, verified, zero leakage.
- The training script refuses to run if the exclude files are missing.
- All generation is greedy (`do_sample=False`): the numbers are deterministic and reproducible.
- `build_holdout.py` records a `source_fingerprint` so benchmark/training data drift is detectable.
