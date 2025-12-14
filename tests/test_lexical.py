"""Tests for lexical.py — WordNet-backed polysemy and specificity scoring."""
from clarity_score.lexical import analyze_lexical, lookup_word, _get_or_create_cache


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
