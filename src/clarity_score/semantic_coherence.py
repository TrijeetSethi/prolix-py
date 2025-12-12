"""Semantic coherence scoring via sentence embeddings (spanIQ-inspired).

Measures whether content words in a sentence are semantically related to each other.
High coherence = words make sense together; low coherence = incongruous or forced vocabulary.

This is orthogonal to SemanticScorer (which measures per-word polysemy). A sentence can
have high individual word specificity but low coherence if those specific words don't
logically relate to each other.

NOT derived from or vendored from spanIQ or any other project. All code reimplemented
from scratch using the embedding model as a black box.

Usage:
    scorer = MiniLMCoherenceScorer()  # loads model lazily (~24MB, cached)
    tokens = tag_sentence("The cat sat.")
    score = scorer.score("The cat sat.", tokens)  # returns ~85-95 for coherent sentences

Model: all-MiniLM-L6-v2 (384-dim sentence embeddings) downloaded lazily.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


# Content word POS tag prefixes (nouns, verbs, adjectives, adverbs)
_CONTENT_TAG_PREFIXES = ("NN", "VB", "JJ", "RB")


def _matches_content_tag(tag: str) -> bool:
    """Check if a POS tag represents a content word."""
    return any(tag.startswith(prefix) for prefix in _CONTENT_TAG_PREFIXES)


def extract_content_words(tokens: Sequence[tuple[str, str]]) -> list[str]:
    """Extract content words from POS-tagged tokens.

    Filters to words that are purely alphabetic and have content-word POS tags.
    Excludes determiners, prepositions, conjunctions, pronouns, etc.
    """
    return [
        token for token, tag in tokens
        if token.isalpha() and _matches_content_tag(tag)
    ]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors (no numpy dependency)."""
    if len(a) != len(b):
        raise ValueError(f"Vector length mismatch: {len(a)} vs {len(b)}")

    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))

    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0

    return dot / (mag_a * mag_b)


def _normalize_vector(v: list[float]) -> list[float]:
    """L2-normalize a vector in place."""
    mag = math.sqrt(sum(x * x for x in v))
    if mag == 0.0:
        return v
    return [x / mag for x in v]


# ============================================================
# Standalone convenience function (mirrors Rust API)
# ============================================================


def sentence_coherence_score(sentence: str, tokens: Sequence[tuple[str, str]]) -> float:
    """Compute coherence score without requiring MiniLM (returns default when no model).

    This is a convenience wrapper that returns a default neutral score of 50.0.
    For actual embedding-based coherence scoring, use MiniLMCoherenceScorer.

    Args:
        sentence: Original sentence text
        tokens: POS-tagged token list from tag_sentence()

    Returns:
        Coherence score on 0-100 scale. Returns 50.0 (neutral) by default;
        returns actual score if scorer is available and content words >= 2.
    """
    content_words = extract_content_words(tokens)

    if len(content_words) < 2:
        return 100.0

    # Default neutral when model not available
    return 50.0


class MiniLMCoherenceScorer:
    """Embedding-based coherence scorer using all-MiniLM-L6-v2.

    The model is loaded lazily on first instantiation and cached internally
    to avoid repeated downloads. Model size: ~24MB. Downloaded to the
    standard sentence-transformers cache directory (~/.cache/huggingface/).

    Requires 'sentence-transformers' package. Install with:
        pip install clarity-score[semantic-coherence]
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        # Lazy import to avoid ImportError on first-class load when feature not installed
        try:
            from sentence_transformers import SentenceTransformer  # noqa: F811
        except ImportError as exc:
            raise ImportError(
                "The 'semantic-coherence' feature requires 'sentence-transformers'.\n"
                "Install it with: pip install clarity-score[semantic-coherence]\n"
                "(or install sentence-transformers directly)\n"
            ) from exc

        self._model = SentenceTransformer(model_name)
        self._model.eval()  # disable dropout, use deterministic embeddings

    # Maximum content words to embed per call for performance.
    # Empirically ~50 words balances quality vs speed even for MPNet (~4s/doc).
    _MAX_WORDS_PER_ENCODE = 50

    def score(self, sentence: str, tokens: Sequence[tuple[str, str]], *, sample_max_words: int | None = None) -> float:
        """Compute contextual coherence for a sentence.

        Algorithm:
            1. Extract content words from POS-tagged tokens
            2. Generate per-word embeddings via the embedding model (batched)
            3. Compute mean pairwise cosine similarity among content words
            4. Map average similarity [-1, 1] to coherence score [10, 100]

        For performance, content words exceeding ``sample_max_words`` (default 50)
        are uniformly sampled to avoid excessive encoding time with larger models.

        Returns:
            Coherence score on 0-100 scale. Higher = more coherent.
            Single content word returns 100 (trivially coherent).
            Two or more words with no semantic relation ~50.
            Very related words (e.g., "soup spoon chef") ~90+.

        Args:
            sentence: Original sentence text (for logging/debugging)
            tokens: POS-tagged token list from tag_sentence()
            sample_max_words: Max content words to encode per call. Defaults to 50.

        Raises:
            ImportError: If the embedding model cannot be loaded (feature not installed)
            ValueError: If content word extraction fails
        """
        content_words = extract_content_words(tokens)

        if len(content_words) < 2:
            return 100.0  # Trivially coherent: single or zero content words

        max_words = sample_max_words or self._MAX_WORDS_PER_ENCODE
        if len(content_words) > max_words:
            # Sample uniformly to keep encoding time manageable
            step = len(content_words) / max_words
            content_words = [content_words[int(i * step)] for i in range(max_words)]

        # Get embeddings (batched for efficiency)
        embeddings = self._model.encode(
            content_words,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=False,
        )

        # embeddings are PyTorch tensors when convert_to_numpy=False; flatten to lists
        if hasattr(embeddings[0], 'tolist'):  # PyTorch tensor
            embeddings = [e.tolist() for e in embeddings]

        n = len(embeddings)

        # Compute mean pairwise cosine similarity
        total_sim = 0.0
        count = 0
        for i in range(n):
            for j in range(i + 1, n):
                sim = _cosine_similarity(embeddings[i], embeddings[j])
                total_sim += sim
                count += 1

        avg_sim = total_sim / max(count, 1)

        # Map cosine similarity [-1, 1] to coherence [10, 100]:
        #   -1 (opposite concepts)    -> ~10 (very incoherent)
        #    0 (no relation)          -> ~50 (neutral)
        #    1 (identical meaning)    -> ~95 (highly coherent)
        raw = 50.0 + avg_sim * 45.0
        return max(10.0, min(100.0, raw))

__all__ = [
    "MiniLMCoherenceScorer",
    "extract_content_words",
    "sentence_coherence_score",
]
