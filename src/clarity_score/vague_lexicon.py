"""Loads the shared vague-word lexicon (fixtures/vague_words.txt, bundled
into this package as clarity_score/data/vague_words.txt -- see
tools/sync_shared_data.py) and flags occurrences in a token sequence.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

# Matches starter.md's per-hit vague-word penalty.
DEFAULT_PENALTY = 15.0


@dataclass(frozen=True)
class VagueHit:
    phrase: str
    penalty: float
    start: int  # index into the word-token sequence passed to find_vague_hits


def _parse_lexicon(text: str) -> frozenset[str]:
    entries = set()
    for line in text.splitlines():
        line = line.strip().lower()
        if not line or line.startswith("#"):
            continue
        entries.add(line)
    return frozenset(entries)


@lru_cache(maxsize=1)
def _default_lexicon() -> frozenset[str]:
    text = (
        resources.files("clarity_score")
        .joinpath("data")
        .joinpath("vague_words.txt")
        .read_text(encoding="utf-8")
    )
    return _parse_lexicon(text)


def find_vague_hits(
    words: Sequence[str],
    *,
    extra_vague_words: str | Iterable[str] | None = None,
) -> list[VagueHit]:
    """Greedily matches the longest vague-lexicon entry (words or
    multi-word phrases, e.g. "kind of") starting at each token position.

    An empty string in words never matches, so it stops a phrase from
    spanning it. A single string passed as extra_vague_words counts as one
    entry. Runs of whitespace in an extra entry count as one space, and an
    empty entry is ignored."""
    if isinstance(extra_vague_words, str):
        extra_vague_words = [extra_vague_words]
    lexicon = _default_lexicon()
    if extra_vague_words:
        extra = {" ".join(w.lower().split()) for w in extra_vague_words}
        lexicon = lexicon | (extra - {""})
    if not lexicon:
        return []

    max_phrase_len = max(len(entry.split()) for entry in lexicon)
    lowered = [w.lower() for w in words]
    n = len(lowered)

    hits: list[VagueHit] = []
    i = 0
    while i < n:
        for length in range(min(max_phrase_len, n - i), 0, -1):
            candidate = " ".join(lowered[i : i + length])
            if candidate in lexicon:
                hits.append(VagueHit(phrase=candidate, penalty=DEFAULT_PENALTY, start=i))
                i += length
                break
        else:
            i += 1
    return hits

__all__ = [
    "VagueHit",
    "find_vague_hits",
]
