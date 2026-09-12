from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# An sdist ships the shared fixtures in tests/fixtures. A checkout keeps them at the repo root.
_LOCAL_FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIXTURES_DIR = _LOCAL_FIXTURES if _LOCAL_FIXTURES.is_dir() else REPO_ROOT / "fixtures"
FIXTURES_PATH = FIXTURES_DIR / "sentences.jsonl"
CLARITY_FIELDS_PATH = FIXTURES_DIR / "clarity_fields.txt"


def load_fixture_sentences() -> list[dict]:
    rows = []
    with FIXTURES_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


@pytest.fixture(scope="session")
def fixture_sentences() -> list[dict]:
    return load_fixture_sentences()


@pytest.fixture(scope="session")
def clarity_fields() -> list[str]:
    """The ClarityScores field names in contract order, shared with the Rust suite."""
    lines = CLARITY_FIELDS_PATH.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]
