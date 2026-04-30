"""The pluggable semantic-ambiguity and coherence scoring interfaces.

The package ships one `SemanticScorer`, `WordnetPolysemyScorer`, which
counts WordNet senses and needs no machine learning dependency. Another
scorer, such as one built on a masked language model, can implement
`SemanticScorer` and be passed to `analyze()` without any change to
`AnalysisResult` or the signature of `analyze()`.

`CoherenceScorer` is the interface for embedding-based contextual coherence
scoring. It measures whether the content words in a sentence relate to each
other, which is independent of per-word polysemy.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol


class SemanticScorer(Protocol):
    """Interface for a semantic ambiguity scorer that analyze() can use."""

    def score(self, sentence: str, words: Sequence[str]) -> float:
        """Returns a semantic-ambiguity score; higher means more ambiguous.
        The value is clamped to 0 to 100 by the pipeline: `analyze()` and
        `extract_primitives()` limit it to that range, so a scorer may return
        more, as `WordnetPolysemyScorer` does for very polysemous words."""
        ...


class WordnetPolysemyScorer:
    """Default `SemanticScorer`: log-scaled average WordNet sense count.

    Uses ln(1 + x) to dampen large sense counts.
    """

    def score(self, sentence: str, words: Sequence[str]) -> float:
        """Return 30 times ln(1 + the mean sense count of words).

        Returns 10.0 when the mean is 1 or less. Higher means more ambiguous
        words. sentence is not used.
        """
        from .lexical import analyze_lexical

        avg_senses = analyze_lexical(words).avg_senses
        if avg_senses > 1:
            return math.log1p(avg_senses) * 30
        return 10.0


# ============================================================
# Coherence scoring
# ============================================================


class CoherenceScorer(Protocol):
    """Interface for embedding-based contextual coherence scoring.

    Measures whether content words in a sentence are semantically related
    to each other. High coherence = words make sense together; low coherence
    = incongruous or forced vocabulary.

    This is orthogonal to SemanticScorer (which measures per-word polysemy).
    A sentence can have high individual word specificity but low coherence
    if those specific words don't logically relate to each other.

    Example: "The quantum device stirred the sandwich with precision" has
    high-specificity words but low coherence — quantum devices don't stir
    sandwiches. A CoherenceScorer would flag this as incoherent despite
    high individual word specificity.
    """

    def score(self, sentence: str, tokens: Sequence[tuple[str, str]]) -> float:
        """Returns coherence score on 0-100 scale. Higher = more coherent."""
        ...

__all__ = [
    "CoherenceScorer",
    "SemanticScorer",
    "WordnetPolysemyScorer",
]
