"""Tests for the CLI integration (subcommands and entry points)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from clarity_score.clarify import clarify
from clarity_score.cli import entry_dir, entry_single


# An sdist ships the shared fixtures in tests/fixtures. A checkout keeps them at the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIXTURE_DIR = (_LOCAL_FIXTURES if _LOCAL_FIXTURES.is_dir() else REPO_ROOT / "fixtures") / "skills"


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

    def test_long_sentence_is_scored_as_text(self, capsys):
        """Text longer than the file name limit is scored, not probed as a path."""
        sentence = "The chef stirred the soup with the spoon. " * 25
        assert entry_single([sentence, "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["sentence"] == sentence

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
        }
        proc = subprocess.run(
            [sys.executable, "-m", "clarity_score.cli", str(skill_md), "--json"],
            capture_output=True, encoding="utf-8", env=env,
        )
        assert proc.returncode == 0, proc.stderr
        assert "\u201d" in json.loads(proc.stdout)["sentence"]

    def test_front_matter_file_scores_like_clarify(self, tmp_path, capsys):
        """A file is read like clarify(): front matter is stripped before scoring."""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(
            "---\nname: demo\ndescription: Helps with various stuff and things\n---\n\n"
            "Run the build script, then open the report in a browser.\n",
            encoding="utf-8",
        )
        assert entry_single([str(skill_md), "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        expected = clarify(skill_md, include_readability=False).to_json()
        assert data["sentence"] == expected["sentence"]
        assert data["clarity_score"] == expected["clarity_score"]

    def test_non_utf8_file_exits_2(self, tmp_path, capsys):
        skill_md = tmp_path / "latin1.md"
        skill_md.write_bytes("Caf\u00e9 menu for the week.\n".encode("latin-1"))
        assert entry_single([str(skill_md), "--json"]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith(f"error: cannot read {skill_md}: ")

    def test_directory_exits_2(self, tmp_path, capsys):
        assert entry_single([str(tmp_path), "--json"]) == 2
        assert "is a directory, use clarity-score-dir" in capsys.readouterr().err

    def test_missing_markdown_file_exits_2(self, tmp_path, capsys):
        assert entry_single([str(tmp_path / "missing.md"), "--json"]) == 2
        assert "error: cannot read" in capsys.readouterr().err

    def test_sentence_ending_in_file_name_is_text(self, capsys):
        assert entry_single(["Update the README.md", "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["sentence"] == "Update the README.md"

    def test_empty_input_exits_2(self, capsys):
        assert entry_single([""]) == 2
        assert "no sentence or file specified" in capsys.readouterr().err


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

    def test_dir_ascii_stdout(self):
        """Directory scan output is plain ASCII, so a non-UTF-8 stdout works."""
        env = {
            **os.environ,
            "PYTHONIOENCODING": "ascii",
        }
        proc = subprocess.run(
            [sys.executable, "-m", "clarity_score.cli", "dir", str(FIXTURE_DIR)],
            capture_output=True, encoding="utf-8", env=env,
        )
        assert proc.returncode == 0, proc.stderr
        assert "ok    specific" in proc.stdout
        assert "ok    vague" in proc.stdout


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

    def test_main_dir_jsonl_pattern(self, tmp_path, capsys):
        """A discovered .jsonl file is scored as one file, not as a batch."""
        from clarity_score.cli import main
        batch = tmp_path / "batch.jsonl"
        batch.write_text(
            '{"path": "demo/SKILL.md", "content": "Run the build script."}\n',
            encoding="utf-8",
        )
        assert main(["dir", str(tmp_path), "-p", "*.jsonl"]) == 0
        captured = capsys.readouterr()
        assert f"ok    {tmp_path.name}" in captured.out
        assert "error" not in captured.err


# ============================================================
# Model comparison (`clarity-score-compare`)
# ============================================================


class _LengthScorer:
    """Coherence scorer stub that needs no embedding model."""

    def __init__(self, model_name: str = "stub"):
        pass

    def score(self, sentence, tokens):
        return float(min(len(sentence), 100))


class _MissingScorer:
    """Coherence scorer stub that fails like a missing sentence-transformers."""

    def __init__(self, model_name: str = "stub"):
        raise ImportError("sentence-transformers is not installed")


class TestModelCompare:
    """Tests for the model comparison statistics and command."""

    SCORES = [("a", 10.0), ("b", 20.0), ("c", 30.0), ("d", 40.0)]

    def test_identical_scores_agree_fully(self):
        from clarity_score.model_compare import _compute_comparison
        m = _compute_comparison("x", "y", self.SCORES, self.SCORES, [], [])
        assert m.rank_agreement_pct == 100.0
        assert m.pearson_r_clarity is None

    def test_rank_agreement_is_symmetric(self):
        from clarity_score.model_compare import _compute_comparison
        other = [("a", 30.0), ("b", 10.0), ("c", 20.0), ("d", 40.0)]
        ab = _compute_comparison("x", "y", self.SCORES, other, [], []).rank_agreement_pct
        ba = _compute_comparison("y", "x", other, self.SCORES, [], []).rank_agreement_pct
        assert ab == ba == pytest.approx(4 / 6 * 100)

    def test_benchmark_scores_each_jsonl_entry(self, tmp_path, monkeypatch, capsys):
        import clarity_score.semantic_coherence as sc
        from clarity_score.model_compare import compare_models_benchmark
        monkeypatch.setattr(sc, "MiniLMCoherenceScorer", _LengthScorer)
        batch = tmp_path / "batch.jsonl"
        batch.write_text(
            '{"path": "one.md", "content": "Run the build."}\n'
            '{"path": "two.md", "content": "Upload the archive to the server."}\n',
            encoding="utf-8",
        )
        result = compare_models_benchmark(["m1", "m2"], batch)
        assert result.n_documents == 2
        assert result.comparisons[0].rank_agreement_pct == 100.0

    def test_compare_models_keys_baseline(self):
        from clarity_score.clarify import compare_models
        skill_md = FIXTURE_DIR / "specific" / "SKILL.md"
        assert list(compare_models(["all-MiniLM-L6-v2"], skill_md)) == ["<baseline>"]

    def test_compare_exits_1_when_no_model_loads(self, tmp_path, monkeypatch, capsys):
        import clarity_score.semantic_coherence as sc
        from clarity_score.cli import main
        monkeypatch.setattr(sc, "MiniLMCoherenceScorer", _MissingScorer)
        output = tmp_path / "comparison.json"
        rc = main(["compare", "--target", str(FIXTURE_DIR), "--output", str(output)])
        assert rc == 1
        assert "no comparison ran" in capsys.readouterr().err
        assert not output.exists()


# ============================================================
# JSON output consistency
# ============================================================


class TestJSONOutput:
    """Verify CLI output matches internal dataclass."""

    def test_single_json_contains_all_fields(self):
        result = entry_single(["The quick brown fox.", "--json"])
        assert result == 0
        captured = subprocess.run(
            [sys.executable, "-c", """
import json, sys
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
