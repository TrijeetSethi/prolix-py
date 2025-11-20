"""clarity_score: syntactic-ambiguity + WordNet-specificity + vagueness
sentence scoring. See ../../ARCHITECTURE.md for the design.

Optional features (install with extras):
    - readability: Flesch-Kincaid, Gunning Fog, SMOG formulas (zero deps)
    - semantic-coherence: embedding-based contextual coherence (requires sentence-transformers)
"""

from .lexical import LexicalReport, WordLexicalInfo, analyze_lexical
from .scorer import SemanticScorer, WordnetPolysemyScorer
from .scoring import AnalysisResult, ScoreWeights, analyze
from .syntax import AmbiguityHit, SyntaxReport, analyze_syntax, tag_sentence
from .vague_lexicon import VagueHit, find_vague_hits
from .clarify import clarify

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

# Optional exports — only available when features are installed.
# These use lazy import so the core package works without any extras.


def _import_readability():
    """Import readability module (always available in this package)."""
    try:
        from . import readability as module
        return module
    except Exception as exc:
        raise ImportError(
            "The 'readability' feature should always be available since it has no external deps.\n"
            f"Import failed: {exc}"
        ) from exc


def _import_semantic_coherence():
    """Import semantic coherence module (requires semantic-coherence extra)."""
    try:
        from . import semantic_coherence as module
        return module
    except ImportError as exc:
        raise ImportError(
            "The 'semantic-coherence' feature requires 'sentence-transformers'.\n"
            "Install it with: pip install clarity-score[semantic-coherence]"
        ) from exc
