"""clarity_score: syntactic-ambiguity + WordNet-specificity + vagueness sentence scoring.

See ../../ARCHITECTURE.md for the design.

Usage::

    from clarity_score import analyze, AnalysisResult, ScoreWeights

    result = analyze("The chef stirred the soup with the spoon.")
    print(result.clarity_score)  # → ~47/100

Optional features (install with extras):
    - readability: Flesch-Kincaid, Gunning Fog, SMOG formulas (zero deps)
    - semantic-coherence: embedding-based contextual coherence (requires sentence-transformers)
"""

from __future__ import annotations

__version__: str = "0.2.0"

from .lexical import LexicalReport, WordLexicalInfo, analyze_lexical
from .scorer import SemanticScorer, WordnetPolysemyScorer
from .scoring import AnalysisResult, ScoreWeights, analyze
from .syntax import AmbiguityHit, SyntaxReport, analyze_syntax, tag_sentence
from .vague_lexicon import VagueHit, find_vague_hits
from .clarify import clarify

__all__ = [
    "__version__",
    "AmbiguityHit",
    "AnalysisResult",
    "LexicalReport",
    "ScoreWeights",
    "SemanticScorer",
    "SyntaxReport",
    "VagueHit",
    "WordLexicalInfo",
    "WordnetPolysemyScorer",
    "analyze",
    "analyze_lexical",
    "analyze_syntax",
    "find_vague_hits",
    "tag_sentence",
]
