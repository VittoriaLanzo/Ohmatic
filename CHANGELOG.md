# Changelog

All notable changes to Ohmatic are recorded here. Ohmatic follows
[Semantic Versioning](https://semver.org). While the version stays below 1.0,
behavior and the circuit schema may change between releases.

## [0.0.3] - 2026-06-24

### Added
- Third-party benchmark on **PCBBench** (PCBSchemaGen v2, MIT): the 62 single-circuit
  tasks scored by Ohmatic's own deterministic ERC verifier, comparing the Ohmatic legs
  (q4 / q8 / bf16) against OpenAI Codex and the untrained Qwen3-8B base. All three
  Ohmatic precisions deliver 0 broken circuits; the untrained base ships 61/62 broken.
  See `eval/benchmark/cross_model/PCBSCHEMAGEN.md`.

### Changed
- The T5 normalizer now guards against subject drift: on an out-of-distribution prompt
  it falls back to the raw prompt instead of substituting a memorized circuit, so a bad
  rewrite cannot corrupt what the generator builds.
- The featured benchmark in the README and on the site is now PCBBench (third-party)
  rather than the in-house prompt set.

## [0.0.2] - 2026-06-20

### Changed
- `ohmatic update` now follows the latest published release tag instead of
  `main`, so a clone tracks tagged releases rather than every commit. Pass
  `--edge` (PowerShell: `-Edge`) to track `main` HEAD for development.

## [0.0.1] - 2026-06-19

The first tagged release. It sets the version baseline and moves distribution
onto GitHub Releases: pushing a `vX.Y.Z` tag verifies the version, runs the
test suite, and publishes a release.

### Added
- Root `VERSION` file as the single source of truth for the product version,
  surfaced by `ohmatic version`.
- Release workflow that checks the tag agrees with `VERSION`, `pyproject.toml`,
  and `frontend/package.json`, runs the tests, then cuts the GitHub Release.

### Changed
- Aligned every product version string to `0.0.1`: `pyproject.toml`,
  `__init__.py`, the frontend package manifest and lockfile, and the UI badge.
  The circuit schema version is independent and stays at `0.1`.

All work merged before this tag is folded into the 0.0.1 baseline.
