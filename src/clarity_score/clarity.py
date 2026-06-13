"""The stable interface of clarity_score: the Clarity class and its ClarityScores result.

Clarity reads the text with the same normalization and tokens as analyze and
reuses the lower level building blocks, but it combines them with its own fixed
formula. Its scores therefore differ from AnalysisResult.clarity_score by design.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass

import nltk

from ._nltk_data import _RESOURCES as _NLTK_RESOURCES
from .lexical import _LEXICON, _get_wordnet, analyze_lexical
from .readability import compute_readability_metrics
from .scoring import _normalize_text, _vague_tokens
from .syntax import analyze_syntax, tag_sentence
from .vague_lexicon import find_vague_hits

_HINT = (
    "Install the language data once with these commands. "
    "python -m nltk.downloader punkt_tab averaged_perceptron_tagger_eng "
    f"and python -m wn download {_LEXICON}"
)

# Sentences are runs of '.', '!' or '?', as in analyze().
_SENTENCE_ENDS = re.compile(r"[.!?]+")


@dataclass(frozen=True, slots=True)
class ClarityScores:
    """Clarity scores for one text.

    Every score runs from 0 to 100 and a higher value always means clearer
    text. Values are rounded to two decimal places. Clarity.score creates
    these objects. Read the scores by attribute name or call to_dict. New
    fields may be added at the end in a minor release, so do not build or
    unpack this object by position.

    Attributes:
        clarity: The headline score. It is the weighted average of the
            lexical, specificity and syntax scores with weights of 0.4, 0.4
            and 0.2.
        lexical: How few dictionary senses the words have. Words with many
            senses, such as make or run, lower it because a reader can pick
            the wrong meaning.
        specificity: How precise the vocabulary is. Specific words such as
            faucet raise it. Vague words such as stuff, thing or various
            lower it.
        syntax: How free the sentences are of structurally ambiguous
            patterns. An example is a prepositional phrase that could
            describe either the verb or the object, as in saw the man with
            the telescope. One such pattern per sentence gives 75.
        readability: The Flesch reading ease score limited to the range from
            0 to 100. A higher value means easier reading. It is reported
            next to the headline and does not change it.
        words: The number of words that were scored. A word is a run of two
            or more letters. Use it to weight averages across several texts.
    """

    clarity: float
    lexical: float
    specificity: float
    syntax: float
    readability: float
    words: int

    def to_dict(self) -> dict[str, float | int]:
        """Return the scores as a plain dictionary.

        The keys are the field names in field order and the values are plain
        floats and integers, so the result can be passed straight to
        json.dumps.
        """
        return asdict(self)


def _require_resources() -> None:
    """Raise LookupError naming the install commands when language data is missing.

    Nothing is downloaded. NLTK_DATA and WN_DATA_DIR are honored.
    """
    for path, package in _NLTK_RESOURCES:
        try:
            nltk.data.find(path)
        except LookupError:
            raise LookupError(f"NLTK data {package} is not installed. {_HINT}") from None
    # WordNet is opened through lexical, which allows threads to share the wn
    # connection only when it is the first to open one.
    try:
        _get_wordnet()
    except LookupError:
        raise LookupError(f"Open English WordNet 2025 is not installed. {_HINT}") from None


def _clamp(value: float) -> float:
    """Limit value to the range 0 to 100, mapping NaN to 0."""
    if not math.isfinite(value):
        return 0.0 if math.isnan(value) else (100.0 if value > 0 else 0.0)
    return min(100.0, max(0.0, value))


class Clarity:
    """Score how clearly a piece of English text is written.

    Create one Clarity object and reuse it for every text you score. The
    object holds only its settings, so it is cheap to keep, it can be shared
    between threads and it can be pickled for use with multiprocessing.

    The headline score combines three signals. Lexical clarity is high when
    the words have few dictionary senses. Specificity is high when the words
    are precise and few vague words appear. Syntax is high when few
    sentences contain structurally ambiguous patterns. The Flesch reading
    ease score is reported next to the headline and does not change it.

    Clarity never downloads anything. Creating it checks that the NLTK
    tokenizer and tagger data and Open English WordNet 2025 are installed.

    Args:
        extra_vague_words: Words or phrases to treat as vague in addition to
            the built in list. Matching ignores case and extra spaces.
            Phrases of several words, such as deal with, are supported.

    Raises:
        LookupError: If the language data is not installed. The message
            lists the commands that install it.
        TypeError: If extra_vague_words is a single string or contains an
            item that is not a string.

    Examples:
        >>> from clarity_score import Clarity
        >>> clarity = Clarity()
        >>> vague = clarity.score("We need to handle some stuff with the thing")
        >>> concrete = clarity.score("We need to replace the leaking kitchen faucet")
        >>> vague.clarity < concrete.clarity
        True
        >>> list(concrete.to_dict())
        ['clarity', 'lexical', 'specificity', 'syntax', 'readability', 'words']

        Words that are vague in your own field lower the specificity score.

        >>> text = "Use synergy to grow the team"
        >>> domain = Clarity(extra_vague_words=["synergy", "leverage"])
        >>> domain.score(text).specificity < clarity.score(text).specificity
        True
    """

    __slots__ = ("_extra_vague_words",)

    def __init__(self, *, extra_vague_words: Iterable[str] = ()) -> None:
        if isinstance(extra_vague_words, str):
            raise TypeError(
                "extra_vague_words must be a collection of strings, not a single string"
            )
        phrases = set()
        for item in extra_vague_words:
            if not isinstance(item, str):
                raise TypeError(f"extra_vague_words items must be str, not {type(item).__name__}")
            # The same Unicode form and ASCII punctuation as the scored text.
            phrase = " ".join(_normalize_text(item).lower().split())
            if phrase:
                phrases.add(phrase)
        self._extra_vague_words: tuple[str, ...] = tuple(sorted(phrases))
        _require_resources()

    def __repr__(self) -> str:
        return f"Clarity(extra_vague_words={list(self._extra_vague_words)!r})"

    # A class with __slots__ needs these to pickle with protocols 0 and 1. The
    # state is a dict, so it is never empty and always reaches __setstate__.
    def __getstate__(self) -> dict[str, tuple[str, ...]]:
        return {"extra_vague_words": self._extra_vague_words}

    def __setstate__(self, state: dict[str, tuple[str, ...]]) -> None:
        self._extra_vague_words = tuple(state["extra_vague_words"])

    def score(self, text: str, /) -> ClarityScores:
        """Score one text.

        The text can be a single sentence or a whole document and is scored
        as one unit. Lexical clarity and specificity are averaged over words
        and syntax is averaged over sentences, so a long text is not
        penalized for its length. Markdown markup is not counted as words.
        The text of code blocks and YAML front matter is scored like prose,
        so remove them first if they should not count.

        Text with no words of two or more letters, such as an empty string or
        a line of digits, scores 0 on every field and words is 0. Check words
        to tell text with nothing to score apart from unclear text.

        This method does not print, log, read files or use the network.

        Args:
            text: The sentence or document to score.

        Returns:
            A ClarityScores object.

        Raises:
            TypeError: If text is not a string.

        Examples:
            >>> scores = Clarity().score("Open the settings page and select Privacy.")
            >>> 0 <= scores.clarity <= 100
            True
            >>> Clarity().score("   ").words
            0
        """
        if not isinstance(text, str):
            raise TypeError(f"text must be str, not {type(text).__name__}")
        text = _normalize_text(text)
        tagged = tag_sentence(text)
        words = [token for token, _tag in tagged if len(token) >= 2 and token.isalpha()]
        if not words:
            # Nothing to score, so every field is 0.
            return ClarityScores(
                clarity=0.0, lexical=0.0, specificity=0.0, syntax=0.0, readability=0.0, words=0
            )

        lexical_report = analyze_lexical(words)
        senses = lexical_report.avg_senses
        lexical = _clamp(100.0 - (30.0 * math.log1p(senses) if senses > 1.0 else 10.0))

        # At most 40 points come off for the share of distinct words that are vague.
        vague = {
            hit.phrase
            for hit in find_vague_hits(
                _vague_tokens(tagged), extra_vague_words=self._extra_vague_words
            )
        }
        vague_ratio = min(1.0, len(vague) / len({word.lower() for word in words}))
        depth_score = min(100.0, lexical_report.avg_depth / 15.0 * 100.0)
        specificity = _clamp(depth_score - 40.0 * vague_ratio)

        sentences = max(1, len(_SENTENCE_ENDS.findall(text)))
        syntax = _clamp(100.0 - 25.0 * analyze_syntax(tagged).ambiguity_score / sentences)

        readability = _clamp(compute_readability_metrics(text).flesch_reading_ease)

        clarity = 0.4 * lexical + 0.4 * specificity + 0.2 * syntax
        return ClarityScores(
            clarity=round(clarity, 2),
            lexical=round(lexical, 2),
            specificity=round(specificity, 2),
            syntax=round(syntax, 2),
            readability=round(readability, 2),
            words=len(words),
        )


__all__ = ["Clarity", "ClarityScores"]
