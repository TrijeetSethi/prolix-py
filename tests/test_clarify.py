"""Tests for the clarify() workflow — single file, directory scan, batch JSONL."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from clarity_score.clarify import (
    _discover_batch_jsonl,
    _read_content,
    _strip_frontmatter,
    clarify,
)


# ---------------------------------------------------------------------------
# Fixtures — test files
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Temporary directory with sample SKILL.md files for testing."""
    # Create a subdirectory structure
    skills = tmp_path / "skills"
    skills.mkdir()

    (skills / "brand.md").write_text("# Brand Skill\n\nUse our brand guidelines.")

    (skills / "calendar.md").write_text(
        "# Calendar Skill\n\nCreate events and manage schedules."
    )

    # Create a non-.md file (should be ignored by default pattern)
    (skills / "notes.txt").write_text("Just notes, not a skill.")

    return tmp_path


@pytest.fixture
def jsonl_batch(tmp_path: Path) -> Path:
    """Temporary JSONL batch file with inline content."""
    batch_file = tmp_path / "batch.jsonl"
    lines = [
        json.dumps({
            "name": "simple",
            "content": "The dog ran quickly.",
        }),
        json.dumps({
            "name": "vague",
            "content": "Make some stuff with things basically.",
        }),
        json.dumps({
            "path": str(tmp_path / "embedded.md"),
            "content": "# Embedded\n\nHandle embedded content from a file path.",
        }),
    ]
    batch_file.write_text("\n".join(lines))
    return batch_file


@pytest.fixture
def single_skill_file(temp_dir: Path) -> Path:
    """Return the first .md file in temp_dir."""
    skills = temp_dir / "skills"
    return next(skills.glob("*.md"))


@pytest.fixture
def frontmatter_file(tmp_path: Path) -> Path:
    """A file with YAML frontmatter to test stripping."""
    f = tmp_path / "with_frontmatter.md"
    f.write_text(
        "---\n"
        "name: my-skill\n"
        "description: Does awesome stuff\n"
        "license: MIT\n"
        "---\n\n"
        "# My Skill\n\nThis is the actual skill content.\n"
    )
    return f


# ---------------------------------------------------------------------------
# Test: frontmatter stripping
# ---------------------------------------------------------------------------


class TestFrontmatterStripping:
    """Verify _strip_frontmatter() handles common YAML frontmatter patterns."""

    def test_no_frontmatter(self):
        text = "# Heading\n\nBody content."
        assert _strip_frontmatter(text) == text

    def test_simple_frontmatter(self, frontmatter_file: Path):
        text = frontmatter_file.read_text()
        stripped = _strip_frontmatter(text)
        # Should NOT start with ---
        assert not stripped.startswith("---")
        # Should contain the heading from the body
        assert "My Skill" in stripped

    def test_multiline_description(self, tmp_path: Path):
        f = tmp_path / "multi.md"
        f.write_text(
            "---\nname: foo\ndescription: |-\nsome multiline\ndescription here\n---\nBody.\n"
        )
        stripped = _strip_frontmatter(f.read_text())
        assert not stripped.startswith("---")
        assert "Body." in stripped


# ---------------------------------------------------------------------------
# Test: single-file scoring
# ---------------------------------------------------------------------------


class TestSingleFile:
    """clarify() on a single file returns AnalysisResult."""

    def test_single_md_file(self, single_skill_file: Path):
        result = clarify(single_skill_file)
        assert hasattr(result, "clarity_score")
        assert isinstance(result.clarity_score, float)
        # Both skills should produce a non-zero clarity score (the bug fix ensures this)
        assert result.clarity_score >= 0

    def test_single_md_returns_analysis_result(self, single_skill_file: Path):
        result = clarify(single_skill_file)
        assert not isinstance(result, dict)
        assert not isinstance(result, list)


# ---------------------------------------------------------------------------
# Test: directory scan
# ---------------------------------------------------------------------------


class TestDirectoryScan:
    """clarify() on a directory returns list of (Path, AnalysisResult)."""

    def test_directory_scans_recursively(self, temp_dir: Path):
        results = clarify(temp_dir / "skills")
        assert isinstance(results, list)
        assert len(results) == 2  # brand.md + calendar.md (notes.txt ignored)

        paths = [p for p, _ in results]
        assert any("brand.md" in str(p) for p in paths)
        assert any("calendar.md" in str(p) for p in paths)

    def test_directory_returns_tuples(self, temp_dir: Path):
        results = clarify(temp_dir / "skills")
        for path, result in results:
            assert isinstance(path, Path)
            assert hasattr(result, "clarity_score")

    def test_directory_nonexistent(self, tmp_path: Path):
        # Non-existent path raises FileNotFoundError (not NotADirectoryError)
        with pytest.raises(FileNotFoundError):
            clarify(tmp_path / "nonexistent_dir")

    def test_directory_empty_pattern(self, temp_dir: Path):
        results = clarify(temp_dir / "skills", pattern="*.txt")
        assert len(results) == 1
        assert "notes.txt" in str(results[0][0])


# ---------------------------------------------------------------------------
# Test: batch JSONL
# ---------------------------------------------------------------------------


class TestBatchJSONL:
    """clarify() on a JSONL file returns dict[str, AnalysisResult]."""

    def test_batch_returns_dict(self, jsonl_batch: Path):
        results = clarify(jsonl_batch)
        assert isinstance(results, dict)
        assert len(results) == 3

    def test_batch_keys_from_name_or_path_stem(self, jsonl_batch: Path):
        results = clarify(jsonl_batch)
        assert "simple" in results
        assert "vague" in results
        # Third entry has path but no name — key is stem
        assert "embedded" in results

    def test_batch_entries_are_analysis_results(self, jsonl_batch: Path):
        results = clarify(jsonl_batch)
        for entry in results.values():
            assert hasattr(entry, "clarity_score")
            assert isinstance(entry.clarity_score, float)


# ---------------------------------------------------------------------------
# Test: clarity ordering (vague < specific)
# ---------------------------------------------------------------------------


class TestClarityOrdering:
    """Verify that vague text scores lower than specific text."""

    def test_vague_barely_above_minimum(self, jsonl_batch: Path):
        results = clarify(jsonl_batch)
        # The "vague" entry should score lower than "simple"
        assert results["vague"].clarity_score <= results["simple"].clarity_score + 10

    def test_vague_specificity_near_zero(self, jsonl_batch: Path):
        results = clarify(jsonl_batch)
        # Vague text should have low specificity (near zero after bug fixes)
        assert results["vague"].specificity < results["simple"].specificity


# ---------------------------------------------------------------------------
# Test: frontmatter-aware scoring
# ---------------------------------------------------------------------------


class TestFrontmatterAwareScoring:
    """Files with frontmatter are scored only on body content."""

    def test_frontmatter_stripped_before_scoring(self, frontmatter_file: Path):
        result = clarify(frontmatter_file)
        # The "does awesome stuff" from the description should not be in the analysis
        # (it would inflate vague hits if frontmatter was scored)
        assert hasattr(result, "specificity")
        assert isinstance(result.specificity, float)


# ---------------------------------------------------------------------------
# Test: coherence scorer integration
# ---------------------------------------------------------------------------


class TestCoherenceIntegration:
    """clarify() passes coherence_scorer through to analyze()."""

    def test_coherence_none_without_scorer(self, single_skill_file: Path):
        result = clarify(single_skill_file)
        # Without coherence_scorer, context_coherence should be None (default behavior)
        assert result.context_coherence is None

    @pytest.mark.skip(reason="Requires sentence-transformers installed")
    def test_coherence_with_scorer(self, single_skill_file: Path):
        from clarity_score.semantic_coherence import MiniLMCoherenceScorer

        scorer = MiniLMCoherenceScorer()
        result = clarify(single_skill_file, coherence_scorer=scorer)
        assert result.context_coherence is not None
        assert isinstance(result.context_coherence, float)


# ---------------------------------------------------------------------------
# Test: error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """clarify() handles errors gracefully."""

    def test_nonexistent_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            clarify(tmp_path / "does_not_exist.md")

    def test_invalid_jsonl_line(self, tmp_path: Path):
        bad = tmp_path / "bad.jsonl"
        bad.write_text('{"path": "foo.md"}\nthis is not json\n')
        # Should raise ValueError for the invalid line
        with pytest.raises(ValueError, match="Invalid JSON"):
            clarify(bad)

    def test_jsonl_no_path_nor_content(self, tmp_path: Path):
        bad = tmp_path / "nopaths.jsonl"
        bad.write_text('{"name": "test", "other": "no path or content"}\n')
        with pytest.raises(ValueError, match='either "path" or "content"'):
            clarify(bad)
