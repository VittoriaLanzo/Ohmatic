# Contributing to Ohmatic

Thanks for your interest in Ohmatic. Contributions are welcome: bug reports, new ERC rules,
circuit examples, documentation, and fixes.

## Before you start

For anything beyond a small fix, open an issue first and describe what you want to change. It saves
you from building something that does not fit the pipeline contracts.

## Development

Ohmatic runs locally with stubs, so you do not need a GPU to work on most of it:

```bash
git clone https://github.com/VittoriaLanzo/Ohmatic.git && cd Ohmatic
./ohmatic start          # Linux/macOS   (.\ohmatic start on Windows)
```

Run the test suite before opening a pull request:

```bash
pip install pytest
pytest tests/ -q
```

CI runs the same suite on Python 3.12 for every pull request to `main`.

## Pull requests

- Keep each pull request focused on one change.
- Match the surrounding code style; do not reformat unrelated files.
- Update or add tests for behavior you change.
- Update the docs if you change a contract.

## Licensing of contributions

Ohmatic is source-available under the [Ohmatic Source-Available License 1.0](LICENSE) (adapted from
the Functional Source License 1.1). By submitting a contribution you agree that it is licensed under
those same terms. Commercial, hosting, and competing-use rights, and acquisition, are described in
[COMMERCIAL.md](COMMERCIAL.md).
