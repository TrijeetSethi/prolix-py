"""Combines the syntactic, lexical/semantic, and vagueness sub-scores into
a single 0-100 clarity score, following starter.md's weighted-formula
shape (fixing its `log1k` bug and generalizing the syntactic-multiplicity
term -- see ../../ARCHITECTURE.md).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .lexical import LexicalReport, analyze_lexical
from .scorer import SemanticScorer, WordnetPolysemyScorer
from .syntax import SyntaxReport, analyze_syntax, tag_sentence
from .vague_lexicon import VagueHit, find_vague_hits


@dataclass(frozen=True)
class ScoreWeights:
    """Mirrors starter.md's `0.4 * semantic + 0.4 * vagueness + 0.2 * syntax`
    blend."""

    semantic: float = 0.4
    vagueness: float = 0.4
    syntax: float = 0.2


@dataclass(frozen=True)
class AnalysisResult:
    sentence: str
    clarity_score: float
    semantic_ambiguity: float
    specificity: float
    syntax: SyntaxReport
    lexical: LexicalReport
    vague_hits: list[VagueHit] = field(default_factory=list)
    weights: ScoreWeights = field(default_factory=ScoreWeights)

    def to_json(self) -> dict:
        return {
            "sentence": self.sentence,
            "clarity_score": round(self.clarity_score, 2),
            "semantic_ambiguity": round(self.semantic_ambiguity, 2),
            "specificity": round(self.specificity, 2),
            "syntax_ambiguity_hits": [
                {"kind": hit.kind, "span": hit.span} for hit in self.syntax.hits
            ],
            "avg_word_senses": round(self.lexical.avg_senses, 2),
            "avg_wordnet_depth": round(self.lexical.avg_depth, 2),
            "vague_word_hits": [
                {"phrase": hit.phrase, "penalty": hit.penalty} for hit in self.vague_hits
            ],
        }


def analyze(
    sentence: str,
    *,
    weights: ScoreWeights | None = None,
    semantic_scorer: SemanticScorer | None = None,
    extra_vague_words: Iterable[str] | None = None,
) -> AnalysisResult:
    weights = weights or ScoreWeights()
    semantic_scorer = semantic_scorer or WordnetPolysemyScorer()

    tagged = tag_sentence(sentence)
    words = [token for token, _tag in tagged if token.isalpha()]

    syntax_report = analyze_syntax(tagged)
    lexical_report = analyze_lexical(words)
    vague_hits = find_vague_hits(words, extra_vague_words=extra_vague_words)

    if not words:
        empty_lexical = LexicalReport()
        return AnalysisResult(
            sentence=sentence,
            clarity_score=0.0,
            semantic_ambiguity=0.0,
            specificity=0.0,
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

    final_ambiguity = (
        semantic_ambiguity * weights.semantic
        + vagueness * weights.vagueness
        + syntax_penalty * weights.syntax
    )
    final_ambiguity = max(0.0, min(final_ambiguity, 100.0))
    clarity_score = 100 - final_ambiguity

    return AnalysisResult(
        sentence=sentence,
        clarity_score=clarity_score,
        semantic_ambiguity=semantic_ambiguity,
        specificity=specificity,
        syntax=syntax_report,
        lexical=lexical_report,
        vague_hits=vague_hits,
        weights=weights,
    )
