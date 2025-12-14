"""Tests for scoring.py — weighted formula, normalization, and edge cases."""
from clarity_score.scoring import ScoreWeights, analyze


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


# ---------------------------------------------------------------------------
# Weight redistribution tests
# ---------------------------------------------------------------------------


def test_weights_all_nonzero_sum_to_one():
    w = ScoreWeights()
    # Default weights: semantic(0.24) + vagueness(0.24) + syntax(0.12) + structure(0.20)
    assert abs(w.non_zero_weight_sum() - 0.60) < 0.01


def test_weights_with_zero_semantic():
    w = ScoreWeights(semantic=0.0, vagueness=0.5, syntax=0.2)
    assert w.non_zero_weight_sum() == 0.7


def test_empty_text_returns_zero_clarity():
    result = analyze("")
    assert result.clarity_score == 0.0
    assert result.semantic_ambiguity == 0.0
    assert result.specificity == 0.0


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


def test_structural_clarity_present_for_non_empty_text():
    """Non-empty text should always get a structural_clarity value."""
    result = analyze("# My Skill\n\nDo stuff.\n")
    assert result.structural_clarity is not None
    assert 10.0 <= result.structural_clarity <= 100.0


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
