"""Checks that the score ranks the shared clear and vague fixtures in order."""

from __future__ import annotations

from pathlib import Path

from clarity_score import clarify

# An sdist ships the shared fixtures in tests/fixtures. A checkout keeps them at the repo root.
_LOCAL_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_REPO_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_DIR = (_LOCAL_FIXTURES if _LOCAL_FIXTURES.is_dir() else _REPO_FIXTURES) / "skills"


def test_specific_skill_outranks_vague_skill():
    specific = clarify(FIXTURE_DIR / "specific" / "SKILL.md")
    vague = clarify(FIXTURE_DIR / "vague" / "SKILL.md")
    assert specific.clarity_score > vague.clarity_score
