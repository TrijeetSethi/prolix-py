from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_PATH = REPO_ROOT / "fixtures" / "sentences.jsonl"


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
