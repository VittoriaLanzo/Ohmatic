# Ohmatic conventions

Every line justifies itself. 600 dense-readable lines beat 1200 padded ones.

## Structure
- Functions over classes. A class earns its keep only with real state
  (e.g. `_Context`'s precomputed indices). No single-implementation Protocols/ABCs.
- One way to do each thing. One source of truth per concept — the prompt,
  ERC feedback, topology resolution, and task prefix each live in exactly one module.
- No parallel stacks. If a path is superseded, delete it — don't leave it importable.

## Flow
- Early returns over elif ladders. A dict dispatch beats a long if-chain.
- Flat over nested: guard-and-continue inside loops, not pyramids.
- Compute invariants once, above the loop — never re-derive per iteration.

## Imports & layout
- No `sys.path.insert`. Pytest gets the root via `conftest.py`; runtime entry
  points run `python -m ...` from the repo root.
- Lazy-import heavy deps (torch, vllm, transformers) inside the function that needs them.

## Errors
- Delete dead code; never comment it out "for later". Git remembers.
- No except-pass theater. Catch only at documented robustness boundaries
  (the ERC analyzer's malformed-input wall) and say why in one line.

## Style
- Comprehensions where they read naturally; never a clever one-liner that doesn't.
- snake_case functions, `_leading_underscore` for module-private.
- Module docstring = WHAT + WHY in 2-4 lines. Not an essay.

## Frozen surfaces (touch internals only, never output bytes)
- `eval.diagnostics.analyze_schematic` — `tests/test_erc_golden.py` (182 circuits)
  must stay byte-identical.
- `shared.prompt_builder.build_system_prompt` — the model trained on those exact bytes.
- `inference.pipeline` public names (`OhmaticPipeline`, `PipelineConfig`,
  `PipelineResult`, `HFChatModel`, `HFT5Normalizer`) — live consumers exist.
- `train/finetune_runpod.py` — regex-patched line-by-line by `finetune_round2.py`;
  do not reformat.
