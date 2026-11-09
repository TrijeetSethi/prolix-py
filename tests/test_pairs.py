"""Checks that the score ranks the shared clear and vague fixtures in order."""

from __future__ import annotations

from pathlib import Path

from clarity_score import clarify

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "skills"


def test_specific_skill_outranks_vague_skill():
    specific = clarify(FIXTURE_DIR / "specific" / "SKILL.md")
    vague = clarify(FIXTURE_DIR / "vague" / "SKILL.md")
    assert specific.clarity_score > vague.clarity_score
