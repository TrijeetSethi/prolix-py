"""Tests for the readability module. Covers:
- Syllable counting accuracy vs known inputs
- Formula correctness (known outputs from academic sources)
- Edge cases (empty text, single word, very long sentences)
- Clarity score mapping consistency
- Integration with full analyze() pipeline
"""

import pytest

from clarity_score.readability import (
    count_sentences,
    count_words,
    count_syllables,
    flesch_reading_ease,
    flesch_kincaid_grade,
    gunning_fog_index,
    smog_index,
    compute_readability_metrics,
    text_to_clarity_score,
)


class TestSyllableCounting:
    """Test syllable counting heuristic against known values."""

    @pytest.mark.parametrize(
        "word,expected",
        [
            ("the", 1),
            ("a", 1),
            ("cat", 1),
            ("dog", 1),
            ("happy", 2),
            ("running", 2),
            ("beautiful", 3),
            ("extraordinary", 5),
            ("strengths", 1),  # 'ght' + 's' — complex consonant cluster
            ("isn't", 2),       # contraction: is-n't → heuristic gives 2
            ("table", 2),       # final 'le' handled
            ("apple", 2),
            ("banana", 3),
            ("communication", 5),
        ],
    )
    def test_known_syllable_counts(self, word: str, expected: int):
        actual = count_syllables(word)
        assert actual == expected, f"{word}: expected {expected}, got {actual}"

    def test_empty_word(self):
        assert count_syllables("") == 0

    def test_punctuation_stripped(self):
        assert count_syllables(".") == 0
        assert count_syllables("...") == 0


class TestSentenceWordCounting:
    """Test sentence and word extraction."""

    @pytest.mark.parametrize(
        "text,expected_sentences",
        [
            ("Hello world.", 1),
            ("Hello. World.", 2),
            ("One! Two? Three!", 3),
            ("No terminators", 1),  # Should default to 1 sentence
            ("", 0),                # Empty → 0 (handled as min(1, ...) elsewhere)
            ("Multiple   spaces.   Here.", 2),
        ],
    )
    def test_sentence_count(self, text: str, expected_sentences: int):
        actual = count_sentences(text)
        if expected_sentences > 0:
            assert actual == max(1, expected_sentences), f"Expected {max(1, expected_sentences)}, got {actual}"
        else:
            assert actual == 0, f"Expected 0 for empty text, got {actual}"

    @pytest.mark.parametrize(
        "text,expected_words",
        [
            ("hello world", 2),
            ("the quick brown fox", 4),
            ("it's a test", 3),      # contraction counted as word(s)
            ("one-two-three", 3),    # hyphens split words
            ("...", 0),
        ],
    )
    def test_word_count(self, text: str, expected_words: int):
        assert len(count_words(text)) == expected_words


class TestFormulaCorrectness:
    """Test formulas against known academic outputs."""

    def test_flesch_reading_ease_known(self):
        # "The cat sat on the mat." — 1 sentence, 6 words, 6 syllables
        # FRE = 206.835 - 1.015*(6/1) - 84.6*(6/6) = 206.835 - 6.09 - 84.6 = 116.145
        result = flesch_reading_ease(1, 6, 6)
        assert abs(result - min(100.0, 116.145)) < 0.1

    def test_flesch_kincaid_grade_known(self):
        # Same text: FKG = 0.39*(6/1) + 11.8*(6/6) - 15.59 = 2.34 + 11.8 - 15.59 = -1.45
        result = flesch_kincaid_grade(1, 6, 6)
        assert abs(result - (-1.45)) < 0.1

    def test_gunning_fog_known(self):
        # Same text: GFI = 0.4 * (6/1 + 100*0/6) = 0.4 * 6 = 2.4
        result = gunning_fog_index(1, 6, 0)
        assert abs(result - 2.4) < 0.1

    def test_smog_known(self):
        # 1 sentence, 0 polysyllabic: SMOG ≈ 1.043 * sqrt(30*0/1) + 3.1291 = 3.1291
        result = smog_index(1, 0)
        assert abs(result - 3.1291) < 0.1

    def test_formula_ranges(self):
        """All formulas should return values within expected ranges."""
        sentence = "This is a very long complicated sentence that contains many polysyllabic words and exceeds normal length"
        long_text = ". ".join([sentence] * 5)

        metrics = compute_readability_metrics(long_text)
        assert 0.0 <= metrics.flesch_reading_ease <= 100.0, "FRE should be [0, 100]"
        assert metrics.flesch_kincaid_grade >= -20.0, "FKG should be reasonable"
        assert metrics.gunning_fog_index >= 0.0, "GFI should be >= 0"
        assert metrics.smog_index >= 0.0, "SMOG should be >= 0"

    def test_empty_text(self):
        result = compute_readability_metrics("")
        # Empty text should not crash; all values can be 0
        assert result.flesch_reading_ease == 0.0


class TestClarityScoreMapping:
    """Test the mapping from readability to clarity scores."""

    def test_easy_text_high_clarity(self):
        easy = "The dog ran."
        score = text_to_clarity_score(easy)
        assert score >= 80.0, f"Easy text should score >= 80, got {score}"

    def test_hard_text_low_clarity(self):
        hard = "The circumnavigation necessitated sophisticated navigational instruments for maritime transit."
        score = text_to_clarity_score(hard)
        assert score <= 65.0, f"Hard text should score <= 65, got {score}"

    def test_floor_at_25(self):
        """Very hard text should not go below floor of 25."""
        very_hard = "The epistemological underpinnings necessitate paradigmatic reorientation."
        score = text_to_clarity_score(very_hard)
        assert score >= 25.0, f"Floor violation: {score}"


class TestIntegrationWithScorer:
    """Test readability integration into the full analyze pipeline."""

    def test_readability_enabled_in_analysis(self):
        from clarity_score.scoring import analyze

        result = analyze("The cat sat.", include_readability=True)
        assert result.readability_score is not None
        assert 25.0 <= result.readability_score <= 100.0

    def test_readability_disabled_defaults_to_none(self):
        from clarity_score.scoring import analyze

        result = analyze("The cat sat.", include_readability=False)
        assert result.readability_score is None

    def test_json_includes_readability_when_present(self):
        from clarity_score.scoring import analyze

        result = analyze("The cat sat.", include_readability=True)
        json_data = result.to_json()
        assert "readability_score" in json_data


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_very_long_sentence(self):
        long = "x " * 500 + "."
        metrics = compute_readability_metrics(long)
        # Should not crash or overflow
        assert isinstance(metrics.flesch_reading_ease, float)

    def test_single_character_words(self):
        # "I a i o u y" — all vowels as words
        text = "I a i o u y"
        metrics = compute_readability_metrics(text)
        # Each is 1 syllable, should give valid scores
        assert isinstance(metrics.smog_index, float)
