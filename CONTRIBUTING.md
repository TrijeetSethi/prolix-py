# Contributing

This repository holds the `prolix` Python package, published on PyPI and
imported as `prolix`. The Rust crate of the same name lives in its own
repository, [prolix-rs](https://github.com/TrijeetSethi/prolix-rs), and follows
the same Clarity contract.

## Set up

```bash
python -m venv .venv
source .venv/bin/activate      # on Windows: .venv\Scripts\activate
pip install -e ".[dev]" "mypy<2"
python -m nltk.downloader punkt_tab averaged_perceptron_tagger_eng
python -m wn download oewn:2025
```

## Checks

CI runs these checks on Python 3.10, 3.12 and 3.14. Run them before you open a
pull request.

```bash
ruff check .
mypy src/prolix
pytest
pytest --doctest-modules src/prolix/clarity.py
```

The coherence tests are skipped unless sentence-transformers is installed.

CI also builds the sdist and the wheel, installs the wheel in a fresh virtual
environment, runs the installed commands and runs the test suite of the
unpacked sdist against the installed wheel.

```bash
pip install build twine
python -m build
twine check --strict dist/*
```

## Shared fixtures

`tests/fixtures` holds the cross-language contract: the test corpus
`sentences.jsonl`, the field order `clarity_fields.txt`, the clear and vague
skill pair in `skills/` and the vague word list `vague_words.txt`. The Rust
crate keeps an identical copy in its own `tests/fixtures`. A change to a
fixture or to scoring logic should be made in both repositories, and both test
suites must keep passing.

`src/prolix/data/vague_words.txt` is the copy of the vague word list
that the package ships. It must stay identical to
`tests/fixtures/vague_words.txt`, and CI fails when the two differ.

## Style

User-facing docs are written in plain prose without em dashes, en dashes,
arrows or tilde approximations, and ranges are written as 0 to 100. CI checks
`README.md`, `CONTRIBUTING.md`, `RELEASING.md` and
`src/prolix/clarity.py` for these characters.

Every public class, method and function has a docstring, which ruff checks.

## Branches and releases

Work lands on `main` through pull requests. The `beta` and `release` branches
publish to PyPI, as described in
[RELEASING.md](https://github.com/TrijeetSethi/prolix-py/blob/main/RELEASING.md).

## License

Unless you explicitly state otherwise, any contribution you intentionally
submit for inclusion in prolix is licensed under the MIT license, without any
additional terms or conditions.
