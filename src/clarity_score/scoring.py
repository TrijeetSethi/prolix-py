"""Combines the syntactic, lexical/semantic, and vagueness sub-scores into
a single 0-100 clarity score, following starter.md's weighted-formula
shape (fixing its `log1k` bug and generalizing the syntactic-multiplicity
term -- see ../../ARCHITECTURE.md).

Added in Phase B: optional readability and coherence signals. These are
feature-gated — when disabled (the default), they contribute zero weight
and AnalysisResult fields are None (not errors). When enabled, they absorb
remaining weight proportionally so the formula always sums to a valid score.

Weight scheme (all signals enabled):
    clarity = 100 - (semantic*0.2 + vagueness*0.15 + syntax*0.05 +
                     (100-readability)*0.30 + (100-coherence)*0.30)
    
Default scheme (only original signals):
    clarity = 100 - (semantic*0.4 + vagueness*0.4 + syntax*0.2)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .scorer import CoherenceScorer  # forward ref — avoid circular import


from .lexical import LexicalReport, analyze_lexical
from .scorer import SemanticScorer, WordnetPolysemyScorer
from .syntax import SyntaxReport, analyze_syntax, tag_sentence
from .vague_lexicon import VagueHit, find_vague_hits


@dataclass(frozen=True)
class ScoreWeights:
    """Mirrors starter.md's `0.4 * semantic + 0.4 * vagueness + 0.2 * syntax`
    blend. Extended in Phase B to support optional readability and coherence.

    When both new signals are enabled, weights redistribute so that all
    five signals sum to 1.0 total weight. When only some are enabled,
    remaining ones absorb the unallocated proportionally.

    Default (backward-compatible): semantic=0.4, vagueness=0.4, syntax=0.2
    """

    semantic: float = 0.4
    vagueness: float = 0.4
    syntax: float = 0.2
    readability: float = 0.0  # NEW — non-zero when feature enabled
    coherence: float = 0.0     # NEW — non-zero when feature enabled

    def non_zero_weight_sum(self) -> float:
        """Sum of all weights that are > 0 (for weight redistribution)."""
        return sum(w for w in [self.semantic, self.vagueness, self.syntax,
                               self.readability, self.coherence] if w > 0.0)


@dataclass(frozen=True)
class AnalysisResult:
    sentence: str
    clarity_score: float
    semantic_ambiguity: float
    specificity: float
    readability_score: Optional[float] = None  # NEW — None when feature not enabled
    context_coherence: Optional[float] = None   # NEW — None when feature not enabled
    syntax: SyntaxReport
    lexical: LexicalReport
    vague_hits: list[VagueHit] = field(default_factory=list)
    weights: ScoreWeights = field(default_factory=ScoreWeights)

    def to_json(self) -> dict:
        data = {
            "sentence": self.sentence,
            "clarity_score": round(self.clarity_score, 2),
            "semantic_ambiguity": round(self.semantic_ambiguity, 2),
            "specificity": round(self.specificity, 2),
            "avg_word_senses": round(self.lexical.avg_senses, 2),
            "avg_wordnet_depth": round(self.lexical.avg_depth, 2),
            "syntax_ambiguity_hits": [
                {"kind": hit.kind, "span": hit.span} for hit in self.syntax.hits
            ],
            "vague_word_hits": [
                {"phrase": hit.phrase, "penalty": hit.penalty} for hit in self.vague_hits
            ],
        }
        # Add optional fields only when present
        if self.readability_score is not None:
            data["readability_score"] = round(self.readability_score, 2)
        if self.context_coherence is not None:
            data["context_coherence"] = round(self.context_coherence, 2)
        return data


def analyze(
    sentence: str,
    *,
    weights: ScoreWeights | None = None,
    semantic_scorer: SemanticScorer | None = None,
    extra_vague_words: Iterable[str] | None = None,
    include_readability: bool = False,
    coherence_scorer: "CoherenceScorer | None" = None,
) -> AnalysisResult:
    """Analyze a sentence's clarity with optional additional signals.

    Args:
        sentence: The sentence to analyze
        weights: Custom score weights (defaults add up to 1.0 across enabled signals)
        semantic_scorer: Semantic scorer for polysemy analysis
        extra_vague_words: Additional vague words to check against
        include_readability: Whether to compute readability metrics (always available — no feature check needed)
        coherence_scorer: Coherence scorer instance. If None and coherence enabled, uses default MiniLMCoherenceScorer.

    Returns:
        AnalysisResult with clarity score and all applicable sub-scores
    """
    weights = weights or ScoreWeights()
    semantic_scorer = semantic_scorer or WordnetPolysemyScorer()

    tagged = tag_sentence(sentence)
    words = [token for token, _tag in tagged if token.isalpha()]

    syntax_report = analyze_syntax(tagged)
    lexical_report = analyze_lexical(words)
    vague_hits = find_vague_hits(words, extra_vague_words=extra_vague_words)

    # Compute readability if requested (always available — no feature check needed)
    readability_score = None
    if include_readability:
        from .readability import text_to_clarity_score as _rto
        readability_score = _rto(sentence)

    # Compute coherence if scorer provided (requires semantic-coherence feature)
    context_coherence = None
    if coherence_scorer is not None:
        try:
            context_coherence = coherence_scorer.score(sentence, tagged)
        except ImportError:
            # Graceful degradation — leave as None
            pass

    if not words:
        empty_lexical = LexicalReport()
        return AnalysisResult(
            sentence=sentence,
            clarity_score=0.0,
            semantic_ambiguity=0.0,
            specificity=0.0,
            readability_score=readability_score,
            context_coherence=context_coherence,
            syntax=syntax_report,
            lexical=empty_lexical,
            vague_hits=vague_hits,
            weights=weights,
        )

    semantic_ambiguity = semantic_scorer.score(sentence, words)

    vague_penalty = sum(hit.penalty for hit in vague_hits)
    specificity = min(lexical_report.avg_depth / 15.0 * 100, 100) - vague_penalty
    specificity = max(0.0, specificity)
    vagueness = 100 - specificity

    syntax_penalty = syntax_report.ambiguity_score * 25

    # ===== WEIGHTED FORMULA WITH REDISTRIBUTION =====
    final_ambiguity = _compute_weighted_ambiguity(
        semantic_ambiguity=semantic_ambiguity,
        vagueness=vagueness,
        syntax_penalty=syntax_penalty,
        readability_score=readability_score,
        coherence_score=context_coherence,
        weights=weights,
    )

    final_ambiguity = max(0.0, min(final_ambiguity, 100.0))
    clarity_score = 100 - final_ambiguity

    return AnalysisResult(
        sentence=sentence,
        clarity_score=clarity_score,
        semantic_ambiguity=semantic_ambiguity,
        specificity=specificity,
        readability_score=readability_score,
        context_coherence=context_coherence,
        syntax=syntax_report,
        lexical=lexical_report,
        vague_hits=vague_hits,
        weights=weights,
    )


def _compute_weighted_ambiguity(
    semantic_ambiguity: float,
    vagueness: float,
    syntax_penalty: float,
    readability_score: Optional[float],
    coherence_score: Optional[float],
    weights: ScoreWeights,
) -> float:
    """Compute weighted ambiguity score with automatic weight redistribution.

    When some signals are absent (None or 0 weight), remaining signals absorb
    their weight proportionally so the formula always sums to a valid score.

    Note: readability_score and coherence_score are already on 0-100 clarity scale
    where higher = better. Vagueness, syntax_penalty, and semantic_ambiguity are
    on 0-100 ambiguity scale where higher = worse.

    For the formula, we invert readability and coherence to the ambiguity scale:
        ambiguity_from_readability = 100 - readability_score
        ambiguity_from_coherence = 100 - coherence_score
    """
    # Build list of (ambiguity_value, weight) for enabled signals
    total_weight = 0.0

    if weights.semantic > 0:
        total_weight += weights.semantic
    if weights.vagueness > 0:
        total_weight += weights.vagueness
    if weights.syntax > 0:
        total_weight += weights.syntax
    if readability_score is not None and weights.readability > 0:
        total_weight += weights.readability
    if coherence_score is not None and weights.coherence > 0:
        total_weight += weights.coherence

    if total_weight == 0:
        # Fallback: unweighted average of available signals
        values = [semantic_ambiguity, vagueness, syntax_penalty]
        if readability_score is not None:
            values.append(100.0 - readability_score)
        if coherence_score is not None:
            values.append(100.0 - coherence_score)
        return max(0.0, min(sum(values) / max(len(values), 1), 100.0))

    weighted_sum = (
        semantic_ambiguity * weights.semantic
        + vagueness * weights.vagueness
        + syntax_penalty * weights.syntax
    )

    if readability_score is not None and weights.readability > 0:
        # Invert: high readability -> low ambiguity contribution
        weighted_sum += (100.0 - readability_score) * weights.readability

    if coherence_score is not None and weights.coherence > 0:
        # Invert: high coherence -> low ambiguity contribution
        weighted_sum += (100.0 - coherence_score) * weights.coherence

    return weighted_sum / total_weight
