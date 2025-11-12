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
