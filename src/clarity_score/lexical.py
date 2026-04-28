"""WordNet-backed polysemy (sense count) and specificity (hypernym depth)
scoring, via the actively-maintained Open English Wordnet (see
../../ARCHITECTURE.md decision #4), replacing starter.md's use of NLTK's
frozen 2006 Princeton WordNet snapshot.

WordNet access is serialized by a module lock, so analyze() can be called
from several threads at once.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass, field

import wn
from wn.morphy import Morphy

_LEXICON = "oewn:2025"
_wordnet: wn.Wordnet | None = None

# Guards the shared wn.Wordnet, its SQLite connection and _word_cache.
_lock = threading.RLock()

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
    """Return the shared Wordnet, creating it on first use.

    wn pools one SQLite connection per database for the whole process, and
    by default that connection only works in the thread that opened it. This
    function sets wn.config.allow_multithreading, which is process-global
    and so also applies to the host application's own use of wn. The flag
    only takes effect when it is set before the first wn connection opens,
    so it has no effect if the host application used wn first.

    Raises LookupError naming the download command when the lexicon is not
    installed.
    """
    global _wordnet
    with _lock:
        if _wordnet is None:
            wn.config.allow_multithreading = True
            try:
                _wordnet = wn.Wordnet(_LEXICON, lemmatizer=Morphy())
            except wn.DatabaseError:
                # A broken or incompatible database is not a missing lexicon.
                raise
            except wn.Error as exc:
                raise LookupError(
                    f"WordNet data {_LEXICON} is not installed. "
                    f"Run: python -m wn download {_LEXICON}"
                ) from exc
        return _wordnet


# Hypernym depth per synset id. Synset.max_depth() walks every hypernym
# path through SQLite and repeats the work for shared ancestors, so the
# depth is memoized per synset instead. Guarded by _lock.
_synset_depth: dict[str, int] = {}


def _max_depth(synset: wn.Synset) -> int:
    """Return the same value as synset.max_depth(), memoized per synset."""
    depth = _synset_depth.get(synset.id)
    if depth is not None:
        return depth
    # Store 0 first so that a cycle in the hypernym graph cannot recurse forever.
    _synset_depth[synset.id] = 0
    hypernyms = synset.get_related("hypernym", "instance_hypernym")
    depth = 1 + max(_max_depth(h) for h in hypernyms) if hypernyms else 0
    _synset_depth[synset.id] = depth
    return depth


@dataclass(frozen=True)
class WordLexicalInfo:
    """WordNet data for one word.

    Attributes:
        word: The word as looked up.
        sense_count: The number of WordNet senses, 1 for a word WordNet does
            not know. Higher means a more ambiguous word.
        avg_max_depth: The mean of the maximum hypernym depth of each sense,
            3.0 for a word WordNet does not know. Higher means a more
            specific word.
    """

    word: str
    sense_count: int
    avg_max_depth: float


@dataclass(frozen=True)
class LexicalReport:
    """WordNet data for every scored word, in input order."""

    words: list[WordLexicalInfo] = field(default_factory=list)

    @property
    def avg_senses(self) -> float:
        """Mean sense_count of the words, or 0.0 when there are none."""
        if not self.words:
            return 0.0
        return sum(w.sense_count for w in self.words) / len(self.words)

    @property
    def avg_depth(self) -> float:
        """Mean avg_max_depth of the words, or 0.0 when there are none."""
        if not self.words:
            return 0.0
        return sum(w.avg_max_depth for w in self.words) / len(self.words)


def lookup_word(word: str) -> WordLexicalInfo:
    """Look up a word in WordNet, using an LRU cache to avoid repeated queries.

    Safe to call from several threads: the whole lookup holds the module lock.
    """
    with _lock:
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
            depths = [_max_depth(s) for s in synsets]
            result = WordLexicalInfo(
                word=word,
                sense_count=len(synsets),
                avg_max_depth=sum(depths) / len(depths),
            )

        cache.put(word, result)
        return result


def analyze_lexical(words: Iterable[str]) -> LexicalReport:
    """Look up every alphabetic word in WordNet and return a LexicalReport.

    Words that are not made only of letters are skipped. Raises
    LookupError naming the download command when the WordNet data is not
    installed.
    """
    return LexicalReport(words=[lookup_word(w) for w in words if w.isalpha()])

__all__ = [
    "LexicalReport",
    "WordLexicalInfo",
    "analyze_lexical",
    "lookup_word",
]
