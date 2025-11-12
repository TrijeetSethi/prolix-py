"""The pluggable semantic-ambiguity scoring interface.

See ../../ARCHITECTURE.md decision #2: v1 ships only `WordnetPolysemyScorer`
(WordNet sense-count based, no ML dependency). A future
`TransformerSemanticScorer` -- sampling a masked-language model's
contextual substitutions, per starter.md's original DeBERTa idea -- can
implement `SemanticScorer` and be passed into `analyze()` without any
change to `AnalysisResult` or `analyze()`'s signature.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol


class SemanticScorer(Protocol):
    def score(self, sentence: str, words: Sequence[str]) -> float:
        """Returns a semantic-ambiguity score, roughly on a 0-100+ scale
        (see `WordnetPolysemyScorer` for the reference implementation's
        range); higher means more ambiguous."""
        ...


class WordnetPolysemyScorer:
    """Default `SemanticScorer`: log-scaled average WordNet sense count.

    Fixes starter.md's `math.log1k` bug (not a real function) -> `math.log1p`.
    """

    def score(self, sentence: str, words: Sequence[str]) -> float:
        from .lexical import analyze_lexical

        avg_senses = analyze_lexical(words).avg_senses
        if avg_senses > 1:
            return math.log1p(avg_senses) * 30
        return 10.0
