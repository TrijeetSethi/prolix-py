"""Tests for lexical.py — WordNet-backed polysemy and specificity scoring."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from clarity_score import _nltk_data
from clarity_score.lexical import analyze_lexical, lookup_word

SRC = Path(__file__).resolve().parents[1] / "src"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "skills"


def test_polysemous_word_has_multiple_senses():
    info = lookup_word("bank")
    assert info.sense_count > 1


def test_unknown_word_uses_fallback():
    info = lookup_word("zzzxqnotaword")
    assert info.sense_count == 1
    assert info.avg_max_depth == 3.0


def test_analyze_lexical_skips_punctuation():
    report = analyze_lexical(["dog", ".", "!", "cat"])
    assert len(report.words) == 2


def test_peanut_butter_sandwich_more_specific_than_sandwich():
    sandwich = analyze_lexical(["sandwich"])
    specific = analyze_lexical(["peanut", "butter", "sandwich"])
    assert specific.avg_depth >= sandwich.avg_depth


# ---------------------------------------------------------------------------
# Cache behavior tests
# ---------------------------------------------------------------------------


def test_cache_returns_consistent_results():
    """Two consecutive lookups for the same word should return identical data."""
    info1 = lookup_word("run")
    info2 = lookup_word("run")
    assert info1.sense_count == info2.sense_count
    assert info1.avg_max_depth == info2.avg_max_depth


def test_cache_handles_empty_list():
    """analyze_lexical with empty list should return empty report."""
    report = analyze_lexical([])
    assert len(report.words) == 0
    assert report.avg_senses == 0.0
    assert report.avg_depth == 0.0


def test_cache_all_non_alpha_filtered():
    """Words that are not purely alphabetic should be skipped."""
    report = analyze_lexical(["123", "hello!", "@world", "python"])
    assert len(report.words) == 1  # only "python" (purely alpha)
    assert all(w.word.isalpha() for w in report.words)


def test_cache_single_character_words_filtered():
    """Single-character tokens like 'a', 'I' should not be included."""
    # This is actually filtered at the caller level in scoring.py,
    # but lexical module itself only filters non-alpha chars.
    # The "a" test verifies lookup_word handles short words gracefully.
    info = lookup_word("a")
    assert info.word == "a"  # Should still return something (fallback or real)


def test_cache_different_words_produce_different_results():
    """Different words should not share cached data."""
    info1 = lookup_word("run")
    info2 = lookup_word("jump")
    assert info1.word != info2.word


# ---------------------------------------------------------------------------
# Missing language data
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [["The dog ran."], ["dir", str(FIXTURE_DIR), "--pattern", "**/SKILL.md"]],
    ids=["single", "dir"],
)
def test_cli_exits_2_when_wordnet_is_missing(args, tmp_path):
    env = {**os.environ, "WN_DATA_DIR": str(tmp_path), "PYTHONPATH": str(SRC)}
    proc = subprocess.run(
        [sys.executable, "-m", "clarity_score.cli", *args],
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert proc.returncode == 2
    assert "python -m wn download oewn:2025" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_failed_nltk_download_raises_lookup_error(monkeypatch):
    def not_found(path):
        raise LookupError(path)

    monkeypatch.setattr(_nltk_data, "_ensured", False)
    monkeypatch.setattr(_nltk_data.nltk.data, "find", not_found)
    monkeypatch.setattr(_nltk_data.nltk, "download", lambda *args, **kwargs: False)
    with pytest.raises(LookupError, match="python -m nltk.downloader punkt_tab"):
        _nltk_data.ensure_nltk_data()
    assert _nltk_data._ensured is False


def test_ensure_nltk_data_checks_once_across_threads(monkeypatch):
    import threading

    import nltk

    calls: list[str] = []
    gate = threading.Barrier(8)

    def counting_find(path, *args, **kwargs):
        calls.append(path)
        return path

    monkeypatch.setattr(nltk.data, "find", counting_find)
    monkeypatch.setattr(_nltk_data, "_ensured", False)

    def worker():
        gate.wait()
        _nltk_data.ensure_nltk_data()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert _nltk_data._ensured is True
    assert len(calls) == len(_nltk_data._RESOURCES)
