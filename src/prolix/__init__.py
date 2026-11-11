"""Score how clearly English text is written.

The Clarity class is the stable interface of this package. Create one
Clarity object, call its score method on a sentence or a document and read
the result. Every score runs from 0 to 100 and a higher value always means
clearer text.

    from prolix import Clarity

    clarity = Clarity()
    scores = clarity.score("Replace the leaking kitchen faucet before Friday")
    print(scores.clarity)

The other functions in this package, such as analyze, clarify and
extract_primitives, form the lower level API. They return more detail and
may change in any minor release before 1.0.
"""

from __future__ import annotations

__version__ = "0.3.0"

from .clarity import Clarity, ClarityScores
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
    # Stable interface
    "Clarity",
    "ClarityScores",
    # Lower level API
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
