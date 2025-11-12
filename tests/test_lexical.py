from clarity_score.lexical import analyze_lexical, lookup_word


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
