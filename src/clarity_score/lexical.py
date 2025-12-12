"""WordNet-backed polysemy (sense count) and specificity (hypernym depth)
scoring, via the actively-maintained Open English Wordnet (see
../../ARCHITECTURE.md decision #4), replacing starter.md's use of NLTK's
frozen 2006 Princeton WordNet snapshot.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass, field

import wn
from wn.morphy import Morphy

_LEXICON = "oewn:2025"
_wordnet: wn.Wordnet | None = None

# Simple LRU cache (max 10K entries) to avoid repeated WordNet lookups
# for the same word across multiple analyze() calls.
class _WordCache:
    """Simple LRU cache mapping word -> WordLexicalInfo."""
    def __init__(self, maxsize: int = 10_000):
        self._cache: OrderedDict[str, WordLexicalInfo] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> WordLexicalInfo | None:
        try:
            value = self._cache.pop(key)
            # Put at end (most recently used)
            self._cache[key] = value
            return value
        except KeyError:
            return None

    def put(self, key: str, value: WordLexicalInfo) -> None:
        try:
            self._cache.pop(key)
        except KeyError:
            pass
        self._cache[key] = value
        # Evict oldest if over capacity
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

_word_cache: _WordCache | None = None


def _get_or_create_cache() -> _WordCache:
    global _word_cache
    if _word_cache is None:
        _word_cache = _WordCache()
    return _word_cache

# Fallback for words with no WordNet entry at all (proper nouns, typos,
# etc.) -- same default starter.md used: `1, 3` (one sense, a shallow
# depth), so unknown words don't get penalized as maximally vague nor
# rewarded as maximally specific.
_FALLBACK_SENSE_COUNT = 1
_FALLBACK_MAX_DEPTH = 3.0


def _get_wordnet() -> wn.Wordnet:
    global _wordnet
    if _wordnet is None:
        _wordnet = wn.Wordnet(_LEXICON, lemmatizer=Morphy())
    return _wordnet


@dataclass(frozen=True)
class WordLexicalInfo:
    word: str
    sense_count: int
    avg_max_depth: float


@dataclass(frozen=True)
class LexicalReport:
    words: list[WordLexicalInfo] = field(default_factory=list)

    @property
    def avg_senses(self) -> float:
        if not self.words:
            return 0.0
        return sum(w.sense_count for w in self.words) / len(self.words)

    @property
    def avg_depth(self) -> float:
        if not self.words:
            return 0.0
        return sum(w.avg_max_depth for w in self.words) / len(self.words)


def lookup_word(word: str) -> WordLexicalInfo:
    """Look up a word in WordNet, using an LRU cache to avoid repeated queries."""
    # Check cache first
    cache = _get_or_create_cache()
    cached = cache.get(word)
    if cached is not None:
        return cached

    synsets = _get_wordnet().synsets(word.lower())
    if not synsets:
        result = WordLexicalInfo(
            word=word,
            sense_count=_FALLBACK_SENSE_COUNT,
            avg_max_depth=_FALLBACK_MAX_DEPTH,
        )
    else:
        depths = [s.max_depth() for s in synsets]
        result = WordLexicalInfo(
            word=word,
            sense_count=len(synsets),
            avg_max_depth=sum(depths) / len(depths),
        )

    cache.put(word, result)
    return result


def analyze_lexical(words: Iterable[str]) -> LexicalReport:
    return LexicalReport(words=[lookup_word(w) for w in words if w.isalpha()])

__all__ = [
    "LexicalReport",
    "WordLexicalInfo",
    "analyze_lexical",
    "lookup_word",
]
