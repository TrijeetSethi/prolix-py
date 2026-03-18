"""clarity_score: syntactic-ambiguity + WordNet-specificity + vagueness sentence scoring.

See ../../ARCHITECTURE.md for the design.

Usage::

    from clarity_score import analyze, AnalysisResult, ScoreWeights

    result = analyze("The chef stirred the soup with the spoon.")
    print(result.clarity_score)  # → ~47/100

Optional features (install with extras):
    - semantic-coherence: embedding-based contextual coherence (requires sentence-transformers)
"""

from __future__ import annotations

__version__: str = "0.2.0"

from .lexical import LexicalReport, WordLexicalInfo, analyze_lexical
from .scorer import SemanticScorer, WordnetPolysemyScorer
from .scoring import AnalysisResult, ScoreWeights, analyze
from .syntax import AmbiguityHit, SyntaxReport, analyze_syntax, tag_sentence
from .vague_lexicon import VagueHit, find_vague_hits
from .clarify import clarify, compare_models
from .readability import ReadabilityMetrics, compute_readability_metrics, text_to_clarity_score
from .structure import StructureReport, analyze_structure
from .primitives import (
    ClarityPrimitives,
    FormulaWeights,
    DEFAULT_WEIGHTS,
    READABILITY_ENABLED_WEIGHTS,
    NO_STRUCTURE_WEIGHTS,
    VAGUENESS_HEAVY_WEIGHTS,
    EVEN_DISTRIBUTION_WEIGHTS,
    apply_all_formulas,
    apply_formula,
    extract_primitives,
    load_primitives,
    save_primitives,
)

__all__ = [
    # Version
    "__version__",
    # Data classes
    "AmbiguityHit",
    "AnalysisResult",
    "LexicalReport",
    "ScoreWeights",
    "StructureReport",
    "SyntaxReport",
    "VagueHit",
    "WordLexicalInfo",
    # Scorer protocols
    "SemanticScorer",
    "WordnetPolysemyScorer",
    # Core API
    "analyze",
    "analyze_lexical",
    "analyze_syntax",
    "tag_sentence",
    "find_vague_hits",
    # Clarify workflow
    "clarify",
    "compare_models",
    # Readability (always available)
    "ReadabilityMetrics",
    "compute_readability_metrics",
    "text_to_clarity_score",
    # Structure (always available)
    "analyze_structure",
    # Primitives & formulas (always available)
    "ClarityPrimitives",
    "FormulaWeights",
    "DEFAULT_WEIGHTS",
    "READABILITY_ENABLED_WEIGHTS",
    "NO_STRUCTURE_WEIGHTS",
    "VAGUENESS_HEAVY_WEIGHTS",
    "EVEN_DISTRIBUTION_WEIGHTS",
    "apply_all_formulas",
    "apply_formula",
    "extract_primitives",
    "load_primitives",
    "save_primitives",
]
