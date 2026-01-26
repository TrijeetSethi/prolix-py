"""Tests for the CLI integration (subcommands and entry points)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Use the package source directly to avoid needing an installed package.
src = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(src))

from clarity_score.cli import entry_dir, entry_single  # noqa: E402


# Fixtures are at repo root, not inside python/
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "fixtures" / "skills"


# ============================================================
# Single-file analysis (legacy CLI)
# ============================================================


class TestSingleFileCLI:
    """Tests for the `clarity-score "sentence"` usage."""

    def test_single_sentence_plain(self):
        result = entry_single(["The cat sat on the mat."])
        assert result == 0

    def test_single_sentence_json(self, capsys):
        result = entry_single(["The cat sat on the mat.", "--json"])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "clarity_score" in data
        assert data["sentence"] == "The cat sat on the mat."

    def test_single_file_json(self, capsys):
        skill_md = FIXTURE_DIR / "specific" / "SKILL.md"
        assert skill_md.is_file()
        result = entry_single([str(skill_md), "--json"])
        assert result == 0
        assert json.loads(capsys.readouterr().out)["sentence"] != str(skill_md)

    def test_whitespace_sentence_json_parses(self, capsys):
        result = entry_single(["   ", "--json"])
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data["clarity_score"] == 0.0

    def test_fail_under_json_exit_code(self, capsys):
        assert entry_single(["Use the thing.", "--json", "--fail-under", "99"]) == 1
        assert json.loads(capsys.readouterr().out)["clarity_score"] < 99

    def test_fail_under_text_exit_code(self, capsys):
        assert entry_single(["Use the thing.", "--fail-under", "99"]) == 1
        assert "Fail:" in capsys.readouterr().err

    @pytest.mark.skipif(sys.platform == "win32", reason="LC_ALL has no effect on Windows")
    def test_utf8_file_under_ascii_locale(self, tmp_path):
        """A UTF-8 file is read as UTF-8 even when the locale encoding is ASCII."""
        skill_md = tmp_path / "quote.md"
        skill_md.write_text("Click \u201cSave\u201d to store the file.\n", encoding="utf-8")
        env = {
            **os.environ,
            "PYTHONUTF8": "0",
            "PYTHONCOERCECLOCALE": "0",
            "LC_ALL": "C",
            "PYTHONPATH": os.pathsep.join(filter(None, [str(src), os.environ.get("PYTHONPATH")])),
        }
        proc = subprocess.run(
            [sys.executable, "-m", "clarity_score.cli", str(skill_md), "--json"],
            capture_output=True, encoding="utf-8", env=env,
        )
        assert proc.returncode == 0, proc.stderr
        assert "\u201d" in json.loads(proc.stdout)["sentence"]


# ============================================================
# Directory scanning (new `clarity-score-dir`)
# ============================================================


class TestDirCLI:
    """Tests for the `clarity-score-dir` subcommand."""

    def test_dir_basic(self, capsys):
        """Directory scan prints each file and summary."""
        result = entry_dir([str(FIXTURE_DIR), "--pattern", "**/SKILL.md"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Found 2" in captured.out  # 2 fixtures
        assert "specific" in captured.out
        assert "vague" in captured.out

    def test_dir_csv_output(self, tmp_path):
        """Directory scan exports to CSV."""
        output = tmp_path / "results.csv"
        result = entry_dir([str(FIXTURE_DIR), "--pattern", "**/SKILL.md", "--output", str(output)])
        assert result == 0
        content = output.read_text(encoding="utf-8")
        assert "clarity_score" in content
        assert "vague" in content
        assert "specific" in content

    def test_dir_json_output(self, tmp_path):
        """Directory scan exports to JSON."""
        output = tmp_path / "results.json"
        result = entry_dir([str(FIXTURE_DIR), "--pattern", "**/SKILL.md", "--output", str(output)])
        assert result == 0
        data = json.loads(output.read_text(encoding="utf-8"))
        # JSON export produces a list of row dicts
        assert isinstance(data, list)
        assert len(data) == 2
        names = [d["name"] for d in data]
        assert "vague" in names
        assert "specific" in names

    def test_dir_nonexistent(self):
        """Directory scan fails gracefully for non-existent path."""
        result = entry_dir(["/nonexistent/path"])
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


# ============================================================
# JSON output consistency
# ============================================================


class TestJSONOutput:
    """Verify CLI output matches internal dataclass."""

    def test_single_json_contains_all_fields(self):
        result = entry_single(["The quick brown fox.", "--json"])
        assert result == 0
        captured = subprocess.run(
            [sys.executable, "-c", f"""
import json, sys
sys.path.insert(0, '{src}')
from clarity_score.cli import entry_single
import io
old = sys.stdout
sys.stdout = io.StringIO()
entry_single(["The quick brown fox.", "--json"])
output = sys.stdout.getvalue()
sys.stdout = old
print(json.loads(output)["clarity_score"])
"""],
            capture_output=True, encoding="utf-8"
        )
        score = float(captured.stdout.strip())
        assert 0 <= score <= 100
