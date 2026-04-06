"""Tests for the CLI integration (subcommands and entry points)."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from clarity_score import Clarity
from clarity_score.clarify import _read_content
from clarity_score.cli import entry_dir, entry_single


# An sdist ships the shared fixtures in tests/fixtures. A checkout keeps them at the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIXTURE_DIR = (_LOCAL_FIXTURES if _LOCAL_FIXTURES.is_dir() else REPO_ROOT / "fixtures") / "skills"

# The keys of ClarityScores.to_dict(), which clarity-score --json prints in this order.
KEYS = ["clarity", "lexical", "specificity", "syntax", "readability", "words"]


# ============================================================
# Single input scoring (the default clarity-score command)
# ============================================================


class TestSingleFileCLI:
    """Tests for the `clarity-score "sentence"` usage."""

    def test_single_sentence_plain(self):
        result = entry_single(["The cat sat on the mat."])
        assert result == 0

    def test_plain_output_is_one_line_per_field(self, capsys):
        text = "The chef stirred the soup with the spoon."
        assert entry_single([text]) == 0
        scores = Clarity().score(text)
        assert capsys.readouterr().out.splitlines() == [
            f"clarity {scores.clarity:.2f}",
            f"lexical {scores.lexical:.2f}",
            f"specificity {scores.specificity:.2f}",
            f"syntax {scores.syntax:.2f}",
            f"readability {scores.readability:.2f}",
            f"words {scores.words}",
        ]

    def test_single_sentence_json(self, capsys):
        result = entry_single(["The cat sat on the mat.", "--json"])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert list(data) == KEYS
        assert data == Clarity().score("The cat sat on the mat.").to_dict()

    def test_single_file_json(self, capsys):
        skill_md = FIXTURE_DIR / "specific" / "SKILL.md"
        assert skill_md.is_file()
        result = entry_single([str(skill_md), "--json"])
        assert result == 0
        expected = Clarity().score(_read_content(skill_md)).to_dict()
        assert json.loads(capsys.readouterr().out) == expected

    def test_long_sentence_is_scored_as_text(self, capsys):
        """Text longer than the file name limit is scored, not probed as a path."""
        sentence = "The chef stirred the soup with the spoon. " * 25
        assert entry_single([sentence, "--json"]) == 0
        assert json.loads(capsys.readouterr().out) == Clarity().score(sentence).to_dict()

    def test_whitespace_sentence_json_parses(self, capsys):
        result = entry_single(["   ", "--json"])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["clarity"] == 0.0
        assert data["words"] == 0
        assert captured.err == "skipped: no words to score\n"

    def test_no_words_passes_fail_under(self, capsys):
        assert entry_single(["1234 5678", "--fail-under", "50"]) == 0
        assert "skipped: no words to score" in capsys.readouterr().err

    def test_fail_under_json_exit_code(self, capsys):
        assert entry_single(["Use the thing.", "--json", "--fail-under", "99"]) == 1
        assert json.loads(capsys.readouterr().out)["clarity"] < 99

    def test_fail_under_text_exit_code(self, capsys):
        assert entry_single(["Use the thing.", "--fail-under", "99"]) == 1
        assert capsys.readouterr().err.startswith("fail: clarity ")

    def test_fail_under_passes_at_threshold(self, capsys):
        clarity = Clarity().score("Use the thing.").clarity
        assert entry_single(["Use the thing.", "--fail-under", str(clarity)]) == 0

    def test_readability_and_coherence_flags_are_gone(self, capsys):
        for flag in ("--readability", "--coherence"):
            with pytest.raises(SystemExit) as exc_info:
                entry_single(["Use the thing.", flag])
            assert exc_info.value.code == 2

    def test_stdin_strips_front_matter(self, monkeypatch, capsys):
        body = "Run the build script, then open the report in a browser.\n"
        stdin = f"---\nname: demo\ndescription: Helps with various stuff\n---\n\n{body}"
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(stdin.encode("utf-8"))))
        assert entry_single(["-", "--json"]) == 0
        assert json.loads(capsys.readouterr().out) == Clarity().score(body).to_dict()

    def test_non_utf8_stdin_exits_2(self, monkeypatch, capsys):
        latin1 = "Café menu for the week.\n".encode("latin-1")
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(latin1)))
        assert entry_single(["-", "--json"]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith("error: cannot read standard input: ")

    def test_stdin_from_a_pipe(self):
        proc = subprocess.run(
            [sys.executable, "-m", "clarity_score", "-", "--json"],
            input="The dog ran.\n", capture_output=True, encoding="utf-8",
        )
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout) == Clarity().score("The dog ran.\n").to_dict()

    @pytest.mark.skipif(sys.platform == "win32", reason="LC_ALL has no effect on Windows")
    def test_utf8_file_under_ascii_locale(self, tmp_path):
        """A UTF-8 file is read as UTF-8 even when the locale encoding is ASCII."""
        text = "Click “Save” to store the file.\n"
        skill_md = tmp_path / "quote.md"
        skill_md.write_text(text, encoding="utf-8")
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
        assert json.loads(proc.stdout) == Clarity().score(text).to_dict()

    def test_front_matter_file_is_stripped(self, tmp_path, capsys):
        """A file is read like clarify(): front matter is stripped before scoring."""
        body = "Run the build script, then open the report in a browser.\n"
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(
            f"---\nname: demo\ndescription: Helps with various stuff and things\n---\n\n{body}",
            encoding="utf-8",
        )
        assert entry_single([str(skill_md), "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data == Clarity().score(body).to_dict()

    def test_non_utf8_file_exits_2(self, tmp_path, capsys):
        skill_md = tmp_path / "latin1.md"
        skill_md.write_bytes("Café menu for the week.\n".encode("latin-1"))
        assert entry_single([str(skill_md), "--json"]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith(f"error: cannot read {skill_md}: ")

    def test_directory_exits_2(self, tmp_path, capsys):
        assert entry_single([str(tmp_path), "--json"]) == 2
        assert "is a directory, use clarity-score dir" in capsys.readouterr().err

    def test_missing_markdown_file_exits_2(self, tmp_path, capsys):
        assert entry_single([str(tmp_path / "missing.md"), "--json"]) == 2
        assert "error: cannot read" in capsys.readouterr().err

    def test_sentence_ending_in_file_name_is_text(self, capsys):
        assert entry_single(["Update the README.md", "--json"]) == 0
        expected = Clarity().score("Update the README.md").to_dict()
        assert json.loads(capsys.readouterr().out) == expected

    def test_empty_input_exits_2(self, capsys):
        assert entry_single([""]) == 2
        assert "no sentence or file specified" in capsys.readouterr().err


# ============================================================
# Directory scanning (`clarity-score dir`)
# ============================================================


class TestDirCLI:
    """Tests for the `clarity-score dir` subcommand."""

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

    def test_main_dir_default_pattern(self, capsys):
        from clarity_score.cli import main
        assert main(["dir", str(FIXTURE_DIR)]) == 0
        assert "Found 2" in capsys.readouterr().out

    def test_main_double_dash_scores_the_word_dir(self, capsys):
        from clarity_score.cli import main
        assert main(["--", "dir"]) == 0
        assert "words 1" in capsys.readouterr().out.splitlines()

    def test_main_dir_version(self, capsys):
        from clarity_score import __version__
        from clarity_score.cli import main
        with pytest.raises(SystemExit) as exc_info:
            main(["dir", "--version"])
        assert exc_info.value.code == 0
        assert capsys.readouterr().out.strip() == f"clarity-score dir {__version__}"

    def test_python_m_version(self):
        from clarity_score import __version__
        proc = subprocess.run(
            [sys.executable, "-m", "clarity_score", "--version"],
            capture_output=True, encoding="utf-8",
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == f"clarity-score {__version__}"

    def test_installed_scripts_run_the_dispatcher(self):
        """The installed clarity-score script is main(), so its subcommands work."""
        from importlib.metadata import PackageNotFoundError, distribution
        try:
            dist = distribution("clarity-score")
        except PackageNotFoundError:
            pytest.skip("clarity-score is not installed")
        scripts = {ep.name: ep.value for ep in dist.entry_points if ep.group == "console_scripts"}
        assert scripts == {
            "clarity-score": "clarity_score.cli:main",
            "clarity-score-dir": "clarity_score.cli:entry_dir",
        }

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


def _run_with_closed_stdout(*args: str) -> tuple[int, str]:
    """Run python -m clarity_score with a stdout pipe that is closed before any output."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "clarity_score", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None and proc.stderr is not None
    proc.stdout.close()
    stderr = proc.stderr.read().decode("utf-8", "replace")
    proc.stderr.close()
    return proc.wait(timeout=120), stderr


class TestBrokenPipe:
    """A reader that closes stdout early, as head does, ends the command quietly."""

    def test_single_exits_0_when_stdout_closes(self):
        assert _run_with_closed_stdout("The chef stirred the soup with the spoon.") == (0, "")

    def test_dir_exits_0_when_stdout_closes(self):
        assert _run_with_closed_stdout("dir", str(FIXTURE_DIR)) == (0, "")


# ============================================================
# Model comparison (deprecated `compare` subcommand)
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
        with pytest.warns(DeprecationWarning, match="removed in clarity-score 0.4.0"):
            result = compare_models_benchmark(["m1", "m2"], batch)
        assert result.n_documents == 2
        assert result.comparisons[0].rank_agreement_pct == 100.0

    def test_compare_models_keys_baseline(self):
        from clarity_score.clarify import compare_models
        skill_md = FIXTURE_DIR / "specific" / "SKILL.md"
        with pytest.warns(DeprecationWarning, match="removed in clarity-score 0.4.0") as record:
            results = compare_models(["all-MiniLM-L6-v2"], skill_md)
        assert list(results) == ["<baseline>"]
        # The warning points at the caller, not at clarity_score.
        assert record[0].filename == __file__

    def test_compare_exits_1_when_no_model_loads(self, tmp_path, monkeypatch, capsys):
        import clarity_score.semantic_coherence as sc
        from clarity_score.cli import main
        monkeypatch.setattr(sc, "MiniLMCoherenceScorer", _MissingScorer)
        output = tmp_path / "comparison.json"
        with pytest.warns(DeprecationWarning, match="removed in clarity-score 0.4.0") as record:
            rc = main(["compare", "--target", str(FIXTURE_DIR), "--output", str(output)])
        assert [w.category for w in record].count(DeprecationWarning) == 1
        assert rc == 1
        assert "no comparison ran" in capsys.readouterr().err
        assert not output.exists()


# ============================================================
# JSON output consistency
# ============================================================


class TestJSONOutput:
    """Verify CLI output matches internal dataclass."""

    def test_single_json_contains_all_fields(self):
        proc = subprocess.run(
            [sys.executable, "-m", "clarity_score", "The quick brown fox.", "--json"],
            capture_output=True, encoding="utf-8",
        )
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout)
        assert list(data) == KEYS
        assert data == Clarity().score("The quick brown fox.").to_dict()
        assert all(0 <= data[key] <= 100 for key in KEYS[:-1])
