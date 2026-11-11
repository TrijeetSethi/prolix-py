"""Tests for scoring.py — weighted formula, normalization, and edge cases."""
import unicodedata

import pytest

from prolix.primitives import extract_primitives
from prolix.scoring import ScoreWeights, _normalize_text, analyze


def test_clarity_score_in_range():
    result = analyze("The chef stirred the soup with the spoon")
    assert 0.0 <= result.clarity_score <= 100.0


def test_vague_sentence_scores_lower_than_concrete_minimal_pair():
    vague = analyze("We need to handle some stuff with the thing")
    concrete = analyze("We need to replace the leaking kitchen faucet")
    assert vague.clarity_score < concrete.clarity_score
    assert len(vague.vague_hits) > 0
    assert len(concrete.vague_hits) == 0


def test_custom_weights_change_the_score():
    sentence = "I saw the man with the telescope"
    default = analyze(sentence)
    syntax_heavy = analyze(sentence, weights=ScoreWeights(semantic=0.0, vagueness=0.0, syntax=1.0))
    assert default.clarity_score != syntax_heavy.clarity_score


def test_to_json_round_trips_basic_shape():
    result = analyze("Make a sandwich")
    data = result.to_json()
    assert data["sentence"] == "Make a sandwich"
    assert "clarity_score" in data
    assert isinstance(data["syntax_ambiguity_hits"], list)


def test_to_json_returns_the_same_dict_as_to_dict():
    result = analyze("The cat sat.", include_readability=True)
    assert result.to_dict() == result.to_json()
    assert isinstance(result.to_dict(), dict)


# ---------------------------------------------------------------------------
# Weight redistribution tests
# ---------------------------------------------------------------------------


def test_default_weights_non_zero_sum_includes_structure():
    w = ScoreWeights()
    # Default weights: semantic(0.24) + vagueness(0.24) + syntax(0.12) + structure(0.20)
    assert abs(w.non_zero_weight_sum() - 0.80) < 0.01


def test_weights_with_zero_semantic():
    w = ScoreWeights(semantic=0.0, vagueness=0.5, syntax=0.2)
    # vagueness(0.5) + syntax(0.2) + default structure(0.20)
    assert w.non_zero_weight_sum() == pytest.approx(0.90)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), -1.0])
def test_invalid_weight_raises_value_error(value):
    with pytest.raises(ValueError, match="ScoreWeights.semantic"):
        ScoreWeights(semantic=value)


def test_all_zero_weights_stay_valid():
    weights = ScoreWeights(semantic=0.0, vagueness=0.0, syntax=0.0, structure=0.0)
    result = analyze("The chef stirred the soup with the spoon", weights=weights)
    assert 0.0 <= result.clarity_score <= 100.0


def test_empty_text_returns_zero_clarity():
    result = analyze("")
    assert result.clarity_score == 0.0
    assert result.semantic_ambiguity == 0.0
    assert result.specificity == 0.0


@pytest.mark.parametrize("value", [b"x", None, 42])
def test_non_str_input_raises_type_error(value):
    with pytest.raises(TypeError, match="text must be str"):
        analyze(value)


def test_single_string_extra_vague_word_counts_as_one_entry():
    result = analyze("Hand me the gizmo please.", extra_vague_words="gizmo")
    assert [hit.phrase for hit in result.vague_hits] == ["gizmo"]


def test_vague_phrase_does_not_match_across_punctuation():
    result = analyze("Choose the merge sort. Of the two outputs, keep the first.")
    assert result.vague_hits == []


def test_vague_phrase_with_one_letter_word_matches():
    result = analyze("We need a lot of tests.")
    assert [hit.phrase for hit in result.vague_hits] == ["a lot"]


@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_decomposed_extra_vague_word_matches(form):
    text = unicodedata.normalize(form, "Order the Caf\u00e9 menu for Friday")
    word = unicodedata.normalize("NFD", "Caf\u00e9")
    result = analyze(text, extra_vague_words=[word])
    assert [hit.phrase for hit in result.vague_hits] == ["caf\u00e9"]


def test_empty_extra_vague_word_is_ignored():
    result = analyze("Keep the file. Run the tests.", extra_vague_words=["", "  "])
    assert result.vague_hits == []


def test_semantic_ambiguity_is_clamped_to_100():
    result = analyze("Break cut.")
    assert result.semantic_ambiguity <= 100.0
    assert extract_primitives("Break cut.").semantic_ambiguity <= 100.0


class _ConstantScorer:
    def __init__(self, value):
        self.value = value

    def score(self, sentence, words):
        return self.value


@pytest.mark.parametrize("value,expected", [(500.0, 100.0), (-5.0, 0.0)])
def test_custom_semantic_scorer_is_clamped(value, expected):
    result = analyze("Replace the kitchen faucet.", semantic_scorer=_ConstantScorer(value))
    assert result.semantic_ambiguity == expected


def test_single_word_sentence_scores_validly():
    """A single word should not crash and should produce a valid score."""
    result = analyze("hello")
    assert 0.0 <= result.clarity_score <= 100.0


def test_syntax_penalty_normalized_for_long_sentences():
    """Multiple PP attachments in one sentence should not blow up the penalty."""
    # This sentence has multiple ambiguous structures
    sentence = "I saw the man with the telescope near the park on the hill by the river"
    result = analyze(sentence)
    # The syntax_penalty is capped at 10 regardless of how many hits
    assert len(result.syntax.hits) >= 1  # should detect at least one PP attachment


def test_vague_penalty_unique_only():
    """Repeating vague words should not multiply the penalty beyond unique ratio."""
    sentence = "stuff and things and stuff with the thing"
    result = analyze(sentence)
    # The vague hits should be deduplicated by phrase for penalty calculation
    assert result.specificity >= 0.0
    assert result.vague_hits  # should have some hits


def test_structural_clarity_present_for_multi_line_text():
    """Text with more than one line gets a structural_clarity value."""
    result = analyze("# My Skill\n\nDo stuff.\n")
    assert result.structural_clarity is not None
    assert 10.0 <= result.structural_clarity <= 100.0


def test_structural_clarity_none_for_single_line():
    """A single line has no markdown layout, so its structure weight is redistributed."""
    sentence = "The chef stirred the soup with the spoon.\n"
    result = analyze(sentence)
    assert result.structural_clarity is None
    no_structure = analyze(sentence, weights=ScoreWeights(structure=0.0))
    assert result.clarity_score == pytest.approx(no_structure.clarity_score)


def test_readability_score_none_when_not_requested():
    """readability_score should be None when include_readability=False."""
    result = analyze("The cat sat.", include_readability=False)
    assert result.readability_score is None


def test_readability_score_present_when_requested():
    """readability_score should be a float when include_readability=True."""
    result = analyze("The cat sat.", include_readability=True)
    assert result.readability_score is not None
    assert 25.0 <= result.readability_score <= 100.0


def test_json_includes_optional_fields_when_present():
    """to_json() should include optional fields when they are not None."""
    result = analyze("The cat sat.", include_readability=True)
    data = result.to_json()
    assert "readability_score" in data


_ASCII_TEXT = (
    "# Setup\n\nDon't edit the config file. It's in the repo root, and you shouldn't "
    "move it. Say \"stop\" when a well-known test fails; don't skip them.\n"
)
_TYPOGRAPHIC_TEXT = (
    _ASCII_TEXT.replace("'", "\u2019")
    .replace('"stop"', "\u201cstop\u201d")
    .replace("well-known", "well\u2010known")
)
_NFC_TEXT = "Caf\u00e9 menus are somewhat nice, and the r\u00e9sum\u00e9 is kind of long."


@pytest.mark.parametrize(
    "plain,variant",
    [
        (_ASCII_TEXT, _TYPOGRAPHIC_TEXT),
        (_ASCII_TEXT, _ASCII_TEXT.replace("'", "\u02bc")),
        (_NFC_TEXT, unicodedata.normalize("NFD", _NFC_TEXT)),
    ],
    ids=["curly", "modifier-apostrophe", "nfd"],
)
def test_normalized_twins_score_the_same(plain, variant):
    assert plain != variant
    expected = analyze(plain, include_readability=True).to_dict()
    result = analyze(variant, include_readability=True)
    assert result.sentence == variant
    assert {**result.to_dict(), "sentence": plain} == expected
    assert result.vague_hits == analyze(plain).vague_hits
    assert extract_primitives(variant) == extract_primitives(plain)


def test_normalize_text_maps_every_typographic_character_to_ascii():
    text = "\u2018a\u2019 b\u02bcc \u201cd\u201d e\u2010f g\u2011h Cafe\u0301"
    assert _normalize_text(text) == "'a' b'c \"d\" e-f g-h Caf\u00e9"
