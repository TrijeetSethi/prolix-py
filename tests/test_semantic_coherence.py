"""Tests for the semantic coherence module. Covers:
- Cosine similarity computation (no numpy dependency)
- Content word extraction from POS tags
- Sentence coherence scoring on known examples
- Graceful degradation when feature not installed
"""

import importlib.util

import pytest


class TestCosineSimilarity:
    """Test the cosine similarity helper function."""

    def test_identical_vectors(self):
        from clarity_score.semantic_coherence import _cosine_similarity

        a = [1.0, 2.0, 3.0]
        b = [1.0, 2.0, 3.0]
        result = _cosine_similarity(a, b)
        assert abs(result - 1.0) < 1e-6

    def test_opposite_vectors(self):
        from clarity_score.semantic_coherence import _cosine_similarity
        a = [1.0, 0.0, 0.0]
        b = [-1.0, 0.0, 0.0]
        assert abs(_cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_orthogonal_vectors(self):
        from clarity_score.semantic_coherence import _cosine_similarity
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert abs(_cosine_similarity(a, b) - 0.0) < 1e-6

    def test_normalized_dot_product(self):
        from clarity_score.semantic_coherence import _cosine_similarity
        # For normalized vectors, cosine similarity = dot product
        a = [1.0 / (2**0.5), 1.0 / (2**0.5)]
        b = [(2**0.5) / 2, (2**0.5) / 2]  # Same direction, different normalization
        assert abs(_cosine_similarity(a, b) - 1.0) < 1e-6

    def test_zero_vector(self):
        from clarity_score.semantic_coherence import _cosine_similarity
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert abs(_cosine_similarity(a, b) - 0.0) < 1e-6


class TestContentWordExtraction:
    """Test that content words are correctly extracted from POS-tagged tokens."""

    def test_nouns_verbs_adjectives_included(self):
        # Nouns (NN), verbs (VB), adjectives (JJ), adverbs (RB) should be included
        tags = [("cat", "NN"), ("sat", "VB"), ("quick", "JJ")]

        from clarity_score.semantic_coherence import _matches_content_tag
        for tag in tags:
            assert _matches_content_tag(tag[1]), f"Tag {tag[1]} should be content"

    def test_function_words_excluded(self):
        # Determiners (DT), prepositions (IN), conjunctions (CC) excluded
        from clarity_score.semantic_coherence import _matches_content_tag
        assert not _matches_content_tag("DT")
        assert not _matches_content_tag("IN")
        assert not _matches_content_tag("CC")
        assert _matches_content_tag("RB")  # Adverbs ARE content words

    def test_extract_content_from_tokens(self):
        from clarity_score.semantic_coherence import extract_content_words
        tokens = [
            ("The", "DT"),      # excluded
            ("quick", "JJ"),    # included
            ("brown", "JJ"),    # included
            ("fox", "NN"),      # included
            ("jumps", "VB"),    # included
            ("over", "IN"),     # excluded
            ("the", "DT"),      # excluded
            ("lazy", "JJ"),     # included
            ("dog", "NN"),      # included
        ]

        result = extract_content_words(tokens)
        assert result == ["quick", "brown", "fox", "jumps", "lazy", "dog"]


class TestSentenceCoherence:
    """Test coherence scoring on sentences with known properties."""

    @pytest.fixture(autouse=True)
    def scorer(self):
        try:
            from clarity_score.semantic_coherence import MiniLMCoherenceScorer
            return MiniLMCoherenceScorer()
        except ImportError:
            pytest.skip("semantic-coherence feature is not installed")

    def test_specific_sentence_has_higher_coherence_than_vague(self, scorer):
        specific = "Assemble a peanut butter and jelly sandwich."
        vague = "Make some stuff with things and handle it basically."

        tokens_specific = [
            ("Assemble", "VB"), ("peanut", "NN"), ("butter", "NN"),
            ("jelly", "NN"), ("sandwich", "NN"),
        ]
        tokens_vague = [
            ("Make", "VB"), ("stuff", "NN"), ("things", "NN"),
            ("handle", "VB"), ("it", "PRP"), ("basically", "RB"),
        ]

        score_specific = scorer.score(specific, tokens_specific)
        score_vague = scorer.score(vague, tokens_vague)

        assert score_specific >= score_vague, (
            f"Specific sentence ({score_specific}) should be more coherent than vague ({score_vague})"
        )

    def test_concrete_sentence_higher_than_incoherent(self, scorer):
        concrete = "The chef stirred the soup with the spoon."
        incoherent = "The quantum device stirred the sandwich with precision."

        tokens_concrete = [
            ("chef", "NN"), ("stirred", "VB"), ("soup", "NN"), ("spoon", "NN")
        ]
        tokens_incoherent = [
            ("quantum", "JJ"), ("device", "NN"), ("stirred", "VB"),
            ("sandwich", "NN"), ("precision", "NN"),
        ]

        score_concrete = scorer.score(concrete, tokens_concrete)
        score_incoherent = scorer.score(incoherent, tokens_incoherent)

        assert score_concrete >= score_incoherent, (
            f"Concrete context ({score_concrete}) should be more coherent than incongruous ({score_incoherent})"
        )

    def test_single_content_word_returns_100(self, scorer):
        score = scorer.score("Cat.", [("Cat", "NN")])
        assert score == 100.0

    def test_score_range(self, scorer):
        """All scores should be in [10, 100]."""
        sentences = [
            "The cat sat.",
            "I saw the man with the telescope.",
            "Assemble a peanut butter sandwich with precision.",
        ]
        for sent in sentences:
            tokens = [(word, "NN") for word in sent.split()]
            score = scorer.score(sent, tokens)
            assert 10.0 <= score <= 100.0, f"Score {score} out of range for: {sent}"


class TestGracefulDegradation:
    """Test that coherence scores gracefully degrade when feature not installed."""

    def test_none_when_scorer_not_available(self):
        """When semantic-coherence feature is not installed,
        coherence_scorer=None should produce None coherence score."""
        from clarity_score.scoring import analyze

        # Without coherence scorer passed, context_coherence should be None
        result = analyze("The cat sat.", coherence_scorer=None)
        assert result.context_coherence is None

    def test_error_message_on_import_failure(self):
        """If someone tries to use MiniLMCoherenceScorer without the feature,
        they get a clear error message."""
        if importlib.util.find_spec("sentence_transformers") is not None:
            pytest.skip("semantic-coherence feature is installed")
        from clarity_score.semantic_coherence import MiniLMCoherenceScorer

        with pytest.raises(ImportError) as excinfo:
            MiniLMCoherenceScorer()
        message = str(excinfo.value).lower()
        assert "semantic-coherence" in message or "feature" in message


class TestIntegrationWithScorer:
    """Test coherence integration into full analyze pipeline."""

    @pytest.fixture(autouse=True)
    def scorer(self):
        try:
            from clarity_score.semantic_coherence import MiniLMCoherenceScorer
            return MiniLMCoherenceScorer()
        except ImportError:
            pytest.skip("semantic-coherence feature is not installed")

    def test_coherence_enabled_in_analysis(self, scorer):
        from clarity_score.scoring import analyze

        result = analyze("The cat sat.", coherence_scorer=scorer)
        assert result.context_coherence is not None
        assert 10.0 <= result.context_coherence <= 100.0

    def test_json_includes_coherence_when_present(self, scorer):
        from clarity_score.scoring import analyze

        result = analyze("The cat sat.", coherence_scorer=scorer)
        json_data = result.to_json()
        assert "context_coherence" in json_data


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_tokens(self):
        from clarity_score.semantic_coherence import extract_content_words, sentence_coherence_score

        # Empty tokens list should not crash
        content = extract_content_words([])
        assert content == []

        # Coherence score on empty tokens should return a valid default
        score = sentence_coherence_score("test", [])
        assert 10.0 <= score <= 100.0, f"Score out of range: {score}"

    def test_non_alpha_tokens_excluded(self):
        from clarity_score.semantic_coherence import extract_content_words

        tokens = [
            ("the", "DT"),
            ("2+2", "NN"),   # non-alpha should be excluded
            ("cat", "NN"),
        ]
        content = extract_content_words(tokens)
        assert content == ["cat"]
