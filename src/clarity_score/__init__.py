"""clarity_score: syntactic-ambiguity + WordNet-specificity + vagueness
sentence scoring. See ../../ARCHITECTURE.md for the design.
"""

from .lexical import LexicalReport, WordLexicalInfo, analyze_lexical
from .scorer import SemanticScorer, WordnetPolysemyScorer
from .scoring import AnalysisResult, ScoreWeights, analyze
from .syntax import AmbiguityHit, SyntaxReport, analyze_syntax, tag_sentence
from .vague_lexicon import VagueHit, find_vague_hits

__all__ = [
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
