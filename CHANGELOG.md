# Changelog

All notable changes to Ohmatic are recorded here. Ohmatic follows
[Semantic Versioning](https://semver.org). While the version stays below 1.0,
behavior and the circuit schema may change between releases.

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
