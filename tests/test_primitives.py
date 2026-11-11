"""Tests for the primitives module (compute-once, apply-formula-many)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gc
import json
import pytest
import tempfile
import warnings
from dataclasses import fields

from prolix.primitives import (
    ClarityPrimitives, FormulaWeights,
    extract_primitives, apply_formula, apply_all_formulas,
    save_primitives, load_primitives,
    _prism_weights, DEFAULT_WEIGHTS,
    NO_STRUCTURE_WEIGHTS,
)
from prolix.scoring import ScoreWeights, analyze


class TestExtractPrimitives:
    """Test that primitives are correctly extracted from text."""

    def test_simple_sentence(self):
        prim = extract_primitives("# Cats\n\nThe cat sat on the mat.", include_readability=True)
        assert 0 <= prim.semantic_ambiguity <= 100
        assert 0 <= prim.specificity <= 100
        assert abs(prim.vagueness - (100 - prim.specificity)) < 0.001
        assert 0 <= prim.syntax_penalty <= 10
        assert prim.readability_score is not None
        assert prim.structural_clarity is not None

    def test_single_line_has_no_structure(self):
        prim = extract_primitives("The cat sat on the mat.\n", include_readability=True)
        assert prim.structural_clarity is None

    def test_no_readability(self):
        prim = extract_primitives("Hello world.", include_readability=False)
        assert prim.readability_score is None

    def test_empty_text(self):
        prim = extract_primitives("", include_readability=True)
        assert prim.semantic_ambiguity == 0.0
        assert prim.specificity == 0.0

    def test_vague_phrase_with_one_letter_word_counts(self):
        text = "We need a lot of tests."
        prim = extract_primitives(text, include_readability=False)
        assert prim.specificity == pytest.approx(analyze(text).specificity, abs=0.001)
        assert prim.specificity < extract_primitives("We need tests.").specificity

    def test_long_text(self):
        text = "The " * 50 + "quick brown fox jumps over the lazy dog. " * 20
        prim = extract_primitives(text, include_readability=True)
        # Should not raise; primitives must handle arbitrary-length input
        assert prim.semantic_ambiguity >= 0


@pytest.mark.parametrize("text", ["", "!!!", "42"])
def test_text_without_scorable_words_scores_zero(text):
    result = analyze(text)
    prim = extract_primitives(text)
    assert result.clarity_score == 0.0
    assert result.word_count == 0
    assert prim.word_count == 0
    assert apply_formula(prim, DEFAULT_WEIGHTS) == 0.0


def test_word_count_counts_words_of_two_or_more_letters():
    text = "We need a lot of tests."
    assert analyze(text).word_count == 5
    assert analyze(text).to_dict()["word_count"] == 5
    assert extract_primitives(text).word_count == 5


def test_primitives_without_word_count_still_combine():
    prim = ClarityPrimitives.from_dict({"semantic_ambiguity": 55.0, "specificity": 30.0,
                                        "vagueness": 70.0, "syntax_penalty": 1.0})
    assert prim.word_count is None
    assert apply_formula(prim, DEFAULT_WEIGHTS) > 0.0


class TestFormulaWeights:
    """Test FormulaWeights configuration."""

    def test_enabled_weight_sum(self):
        # Default weights (structure=0.20) are included; only explicitly
        # overridden fields matter — the remaining defaults stay in place.
        w = FormulaWeights(semantic=0.3, vagueness=0.2)
        assert w.enabled_weight_sum() == pytest.approx(0.5 + 0.12 + 0.20)  # syntax + structure remain default

    def test_zero_weight_excluded(self):
        # Zero-weight fields are excluded; defaults for structure & coherence remain.
        w = FormulaWeights(readability=0.15, syntax=0.0)
        assert w.enabled_weight_sum() == pytest.approx(0.24 + 0.24 + 0.15 + 0.20)  # semantic + vagueness + readability + structure


class TestApplyFormula:
    """Test formula application on primitives."""

    @pytest.fixture
    def sample_prims(self):
        return extract_primitives(
            "The quick brown fox jumps over the lazy dog.",
            include_readability=True,
        )

    def test_default_formula_returns_valid_score(self, sample_prims):
        score = apply_formula(sample_prims, DEFAULT_WEIGHTS)
        assert 0 <= score <= 100

    def test_custom_weights_applied(self, sample_prims):
        custom = FormulaWeights(semantic=1.0, vagueness=0.0, syntax=0.0, structure=0.0)
        score_heavy_sem = apply_formula(sample_prims, custom)
        # High semantic ambiguity → higher final clarity (since we're on ambiguity scale)
        assert score_heavy_sem > 30

    def test_all_zeros_fallback(self, sample_prims):
        zero_w = FormulaWeights()  # all zeros
        score = apply_formula(sample_prims, zero_w)
        # Should fall back to unweighted average
        assert 0 <= score <= 100

    def test_no_structure_formula(self, sample_prims):
        score = apply_formula(sample_prims, NO_STRUCTURE_WEIGHTS)
        assert 0 <= score <= 100


_AGREEMENT_TEXTS = [
    "The chef stirred the soup with the spoon.",
    "Use the thing to do stuff.",
    "# Deploy\n\n## Steps\n1. Run the build.\n2. Upload the archive to the server.\n",
]


@pytest.mark.parametrize("name,fw", _prism_weights(), ids=[n for n, _ in _prism_weights()])
@pytest.mark.parametrize("text", _AGREEMENT_TEXTS, ids=["sentence", "vague", "markdown"])
def test_apply_formula_matches_analyze(name, fw, text):
    """Every preset gives the score analyze() gives for the same weights."""
    same = ScoreWeights(**{f.name: getattr(fw, f.name) for f in fields(ScoreWeights)})
    expected = analyze(text, weights=same, include_readability=True).clarity_score
    assert apply_formula(extract_primitives(text), fw) == pytest.approx(expected, abs=0.01)


class TestApplyAllFormulas:
    """Test applying all 5 formula presets at once."""

    def test_returns_five_scores(self):
        prim = extract_primitives("Test sentence here.", include_readability=True)
        scores = apply_all_formulas(prim)
        assert len(scores) == 5
        # Each score should be valid
        for name, score in scores.items():
            assert 0 <= score <= 100

    def test_formula_names_match_presets(self):
        prim = extract_primitives("test text.", include_readability=True)
        scores = apply_all_formulas(prim)
        expected = {"default", "readability_enabled", "no_structure",
                    "vagueness_heavy", "even_distribution"}
        assert set(scores.keys()) == expected


class TestSaveLoadRoundTrip:
    """Test JSONL serialization/deserialization."""

    def test_round_trip_single(self):
        prim = extract_primitives("Hello world.", include_readability=True)
        
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            tmp_path = Path(f.name)
        
        try:
            save_primitives(tmp_path, [{"commit": "abc123", "primitives": prim}])
            loaded = load_primitives(tmp_path)
            
            assert len(loaded) == 1
            loaded_prim = loaded[0]["primitives"]
            assert isinstance(loaded_prim, ClarityPrimitives)
            assert abs(loaded_prim.semantic_ambiguity - prim.semantic_ambiguity) < 0.01
        finally:
            tmp_path.unlink()

    def test_round_trip_multiple(self):
        primes = [extract_primitives(f"Document {i}.", include_readability=True) for i in range(3)]
        
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            tmp_path = Path(f.name)
        
        rows = [{"commit": f"hash{i}", "primitives": p} for i, p in enumerate(primes)]
        
        try:
            save_primitives(tmp_path, rows)
            loaded = load_primitives(tmp_path)
            
            assert len(loaded) == 3
            for orig, new in zip(primes, [r["primitives"] for r in loaded]):
                assert abs(new.semantic_ambiguity - orig.semantic_ambiguity) < 0.01
        finally:
            tmp_path.unlink()

    def test_load_ignores_unknown_keys(self, tmp_path):
        """A record with an extra key and no optional fields still loads."""
        prims = {"semantic_ambiguity": 55.0, "specificity": 30.0, "vagueness": 70.0,
                 "syntax_penalty": 1.0, "new_signal": 12.0}
        path = tmp_path / "p.jsonl"
        path.write_text(json.dumps({"commit_hash": "abc123", "primitives": prims}) + "\n",
                        encoding="utf-8")
        loaded = load_primitives(path)[0]["primitives"]
        assert isinstance(loaded, ClarityPrimitives)
        assert loaded.semantic_ambiguity == 55.0
        assert loaded.readability_score is None

    def test_load_closes_file(self, tmp_path):
        path = tmp_path / "p.jsonl"
        prim = extract_primitives("Hello world.", include_readability=True)
        save_primitives(path, [{"commit_hash": "abc123", "primitives": prim}])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            load_primitives(path)
            gc.collect()
        assert not [w for w in caught if issubclass(w.category, ResourceWarning)]


class TestPrismWeights:
    """Test the default formula grid."""

    def test_returns_five_formulas(self):
        formulas = _prism_weights()
        assert len(formulas) == 5
    
    def test_formula_names_unique(self):
        formulas = _prism_weights()
        names = [name for name, _ in formulas]
        assert len(names) == len(set(names))
