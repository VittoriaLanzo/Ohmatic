# Ohmatic Testing Guide

Ohmatic is a Python pipeline (T5 normalizer -> fine-tuned Qwen3-8B -> ERC verification
-> self-correction loop -> killswitch) behind a local gateway, with a React frontend that
only visualizes the result. The two CI gates are `pytest tests/` and the launcher smoke
test; everything below expands on those.

## Prerequisites

- Python 3.10+  ->  `pip install -r requirements.txt`
- Node.js 18+ (frontend)  ->  `cd frontend && npm install`

## Python tests

CI: `.github/workflows/python-package.yml`

```
pytest tests/ -q
```

Covers the verification core and the data/serving contracts:

- `test_diagnostics.py`, `test_erc_golden.py` - the ERC engine
  (`eval.diagnostics.analyze_schematic`), the single source of truth shared by training,
  the benchmark, and the gateway. The golden test pins ERC output byte-for-byte over the
  checked-in circuits.
- `test_dataset_validator.py`, `test_teacher_corpus.py` - schema validation and the
  teacher-corpus compiler (both read `verifier/config/component_registry.toml`).
- `test_parts_list.py`, `test_procurement_linkout.py`, `test_jameco_procurement_contract.py`
  - the parts-list / procurement helpers.
- `test_gateway_jobs.py` - the gateway job-lifecycle contract (submit -> poll ->
  done/failed, the killswitch refusal, single-port bind).
- `test_tensor_alignment.py`, `test_eval_metadata_contract.py`, `test_log_schema_contract.py`
  - training-feature alignment and the eval/log schema contracts.

## Frontend tests

```
cd frontend
npm run lint    # tsc type-check
npm test        # vitest
```

The `SchematicSvg` tests render every known component type and every checked-in dataset
example, so any ERC-passing circuit is guaranteed to render.

## End-to-end (the launcher)

```
./ohmatic doctor   # probe hardware (RAM/VRAM), recommend a model tier
./ohmatic start    # gateway (:8080) + frontend (:5173); open the printed URL
```

CI launch-smoke (`.github/workflows/launch-smoke.yml`, Ubuntu + macOS) boots the stack
with no model installed and asserts the gateway answers `model_not_installed` and that
`/v1/verify` returns ERC diagnostics - i.e. the stack is wired correctly before any weights
are fetched. To run a real generation, fetch a model first:

```
./ohmatic fetch    # downloads the doctor-recommended tier into models/ (needs HF access)
./ohmatic start    # then generate from the UI
```

## Benchmark (optional)

The cross-model benchmark lives in `eval/benchmark/cross_model/`:

```
python -m eval.benchmark.cross_model.generate --model q4 --suite realuser
python -m eval.benchmark.cross_model.verify
python -m eval.benchmark.cross_model.report --suite realuser
```

`generate` is the only stage that costs GPU/money; `verify` and `report` are free and
rerunnable. Raw outputs land in the gitignored `results/` / `verified/`.
