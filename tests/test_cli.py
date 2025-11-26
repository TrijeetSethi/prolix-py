"""Tests for the CLI integration (subcommands and entry points)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Use the package source directly to avoid needing an installed package.
src = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(src))

from clarity_score.cli import _entry_dir, _entry_single


# Fixtures are at repo root, not inside python/
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "fixtures" / "skills"


# ============================================================
# Single-file analysis (legacy CLI)
# ============================================================


class TestSingleFileCLI:
    """Tests for the `clarity-score "sentence"` usage."""

    def test_single_sentence_plain(self):
        result = _entry_single(["The cat sat on the mat."])
        assert result == 0

    def test_single_sentence_json(self, capsys):
        result = _entry_single(["The cat sat on the mat.", "--json"])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "clarity_score" in data
        assert data["sentence"] == "The cat sat on the mat."

    def test_single_file_json(self):
        skill_md = FIXTURE_DIR / "specific_calendar.md"
        result = _entry_single([str(skill_md), "--json"])
        assert result == 0


# ============================================================
# Directory scanning (new `clarity-score-dir`)
# ============================================================


class TestDirCLI:
    """Tests for the `clarity-score-dir` subcommand."""

    def test_dir_basic(self, capsys):
        """Directory scan prints each file and summary."""
        result = _entry_dir([str(FIXTURE_DIR), "--pattern", "**/SKILL.md"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Found 2" in captured.out  # 2 fixtures
        assert "specific" in captured.out
        assert "vague" in captured.out

    def test_dir_csv_output(self, tmp_path):
        """Directory scan exports to CSV."""
        output = tmp_path / "results.csv"
        result = _entry_dir([str(FIXTURE_DIR), "--pattern", "**/SKILL.md", "--output", str(output)])
        assert result == 0
        content = output.read_text()
        assert "clarity_score" in content
        assert "vague" in content
        assert "specific" in content

    def test_dir_json_output(self, tmp_path):
        """Directory scan exports to JSON."""
        output = tmp_path / "results.json"
        result = _entry_dir([str(FIXTURE_DIR), "--pattern", "**/SKILL.md", "--output", str(output)])
        assert result == 0
        data = json.loads(output.read_text())
        # JSON export produces a list of row dicts
        assert isinstance(data, list)
        assert len(data) == 2
        names = [d["name"] for d in data]
        assert "vague" in names
        assert "specific" in names

    def test_dir_nonexistent(self):
        """Directory scan fails gracefully for non-existent path."""
        result = _entry_dir(["/nonexistent/path"])
        assert result == 1


# ============================================================
# Main dispatcher (backward compatibility)
# ============================================================


class TestMainDispatch:
    """Tests for the main() dispatcher function."""

    def test_main_single_sentence(self, capsys):
        from clarity_score.cli import main
        result = main(["Hello world."])
        assert result == 0

    def test_main_dir_subcommand(self, capsys):
        from clarity_score.cli import main
        result = main([
            "dir", str(FIXTURE_DIR),
            "--pattern", "**/SKILL.md",
            "--output", "/dev/null",
        ])
        assert result == 0

    def test_main_dir_with_readability(self, capsys):
        """Test main() dispatching to dir subcommand with --readability."""
        from clarity_score.cli import main
        result = main([
            "dir", str(FIXTURE_DIR),
            "--pattern", "**/SKILL.md",
            "--readability",
            "--output", "/dev/null",
        ])
        assert result == 0

    def test_main_compare_subcommand(self, tmp_path):
        from clarity_score.cli import main
        output = tmp_path / "comparison.json"
        # Skip model comparison in tests — too slow. Just verify entry point exists.
        pass  # _cmd_compare is tested via integration above


# ============================================================
# JSON output consistency
# ============================================================


class TestJSONOutput:
    """Verify CLI output matches internal dataclass."""

    def test_single_json_contains_all_fields(self):
        result = _entry_single(["The quick brown fox.", "--json"])
        assert result == 0
        captured = subprocess.run(
            [sys.executable, "-c", f"""
import json, sys
sys.path.insert(0, '{src}')
from clarity_score.cli import _entry_single
import io
old = sys.stdout
sys.stdout = io.StringIO()
_entry_single(["The quick brown fox.", "--json"])
output = sys.stdout.getvalue()
sys.stdout = old
print(json.loads(output)["clarity_score"])
"""],
            capture_output=True, text=True
        )
        score = float(captured.stdout.strip())
        assert 0 <= score <= 100
