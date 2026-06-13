"""Combines the semantic, vagueness, syntax and structure sub-scores, and the
optional readability and coherence signals, into a single clarity score from
0 to 100. The score is 100 minus a weighted average of the ambiguity of each
signal.

Readability and coherence are optional signals. readability_score is
computed when include_readability is set and context_coherence when a
coherence scorer is passed, and each is None otherwise. Either one changes
clarity_score only when its weight is above 0. Both weights are 0 by
default, so with the default weights these signals are reported and do not
change the score.

Weighted formula:
    ambiguity = (semantic*w_semantic + vagueness*w_vagueness + syntax*w_syntax
                 + (100-structure)*w_structure + (100-readability)*w_readability
                 + (100-coherence)*w_coherence) / (sum of the counted weights)
    clarity = 100 - ambiguity, with ambiguity clamped to the range 0 to 100

The syntax term is a penalty from 0 to 10 and every other term runs from 0
to 100. A weight counts only when it is above 0 and, for structure,
readability and coherence, only when that signal was computed. The default weights are
semantic 0.24, vagueness 0.24, syntax 0.12 and structure 0.20, with
readability and coherence at 0. They add up to 0.80, so after the division
they act as 0.30, 0.30, 0.15 and 0.25. Structure is computed only for text
with more than one line, so with the defaults a single line scores with 0.4,
0.4 and 0.2. If no weight counts, ambiguity is the unweighted mean of the
available signals.
"""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .scorer import CoherenceScorer  # forward ref — avoid circular import


import re

from .lexical import LexicalReport, analyze_lexical
from .scorer import SemanticScorer, WordnetPolysemyScorer
from .syntax import SyntaxReport, analyze_syntax, tag_sentence
from .vague_lexicon import VagueHit, find_vague_hits


# Typographic apostrophes, quotes and hyphens map to their ASCII forms, which
# the tokenizer and tagger handle, for example to split "don't" into "do" and
# "n't".
_TYPOGRAPHIC_TO_ASCII = str.maketrans({
    "\u2018": "'",
    "\u2019": "'",
    "\u02bc": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2010": "-",
    "\u2011": "-",
})


def _normalize_text(text: str) -> str:
    """Return text in Unicode NFC form with typographic apostrophes, double
    quotes and hyphens replaced by their ASCII forms, so text from a word
    processor scores the same as the same text typed in ASCII."""
    return unicodedata.normalize("NFC", text).translate(_TYPOGRAPHIC_TO_ASCII)


def _vague_tokens(tagged: Sequence[tuple[str, str]]) -> list[str]:
    """Return the tokens that vague phrases are matched against.

    Every alphabetic token is kept, including one-letter words such as the
    'a' in 'a lot'. Every other token, such as punctuation, becomes an empty
    string, so a phrase cannot match across it.
    """
    return [token if token.isalpha() else "" for token, _tag in tagged]


@dataclass(frozen=True)
class ScoreWeights:
    """Weights of the signals in the clarity formula.

    Defaults: semantic 0.24, vagueness 0.24, syntax 0.12, structure 0.20,
    readability 0 and coherence 0. The weights do not need to add up to 1,
    because analyze() divides by the sum of the weights of the signals that
    are present. The defaults add up to 0.80 and so act as 0.30, 0.30, 0.15
    and 0.25. Structure is present only for text with more than one line, so
    with the defaults a single line scores with 0.4, 0.4 and 0.2. If every
    weight is 0, analyze() uses the unweighted mean of the available signals.

    Raises ValueError if any weight is negative, NaN or infinite.
    """

    semantic: float = 0.24
    vagueness: float = 0.24
    syntax: float = 0.12
    readability: float = 0.0   # above 0 to count readability_score in the score
    coherence: float = 0.0     # above 0 to count context_coherence in the score
    structure: float = 0.20    # structural clarity (always available)

    def __post_init__(self) -> None:
        # All-zero weights stay valid: they select the unweighted mean fallback.
        for f in fields(self):
            value = getattr(self, f.name)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(
                    f"ScoreWeights.{f.name} must be a finite number of 0 or more, got {value!r}"
                )

    def non_zero_weight_sum(self) -> float:
        """Sum of all weights that are > 0 (for weight redistribution)."""
        return sum(w for w in [self.semantic, self.vagueness, self.syntax,
                               self.readability, self.coherence, self.structure]
                   if w > 0.0)


@dataclass(frozen=True)
class AnalysisResult:
    """The result of analyze(), with the clarity score and every signal.

    Attributes:
        sentence: The text as given to analyze().
        clarity_score: 0 to 100. Higher means clearer text.
        semantic_ambiguity: 0 to 100. Higher means words with more dictionary
            senses, so less clear text.
        specificity: 0 to 100. Higher means more specific words and fewer
            vague ones, so clearer text.
        syntax: The structural ambiguity hits. More hits mean less clear text.
        lexical: The WordNet sense count and depth of every scored word.
        vague_hits: The vague words and phrases found in the text.
        weights: The ScoreWeights used for clarity_score.
        readability_score: 25 to 100, or None unless include_readability is
            set. Higher means easier to read.
        context_coherence: 0 to 100, or None unless a coherence scorer is
            passed. Higher means words that relate to each other more.
        structural_clarity: 10 to 100, or None for text with a single line.
            Higher means better markdown structure.
    """

    sentence: str
    clarity_score: float
    semantic_ambiguity: float
    specificity: float
    syntax: SyntaxReport
    lexical: LexicalReport
    vague_hits: list[VagueHit] = field(default_factory=list)
    weights: ScoreWeights = field(default_factory=ScoreWeights)
    readability_score: Optional[float] = None
    context_coherence: Optional[float] = None
    structural_clarity: Optional[float] = None

    @property
    def word_count(self) -> int:
        """Number of scored words, the tokens of two or more letters. It is
        0 when the text has none, and clarity_score is then 0.0."""
        return len(self.lexical.words)

    def to_dict(self) -> dict:
        """Return the result as a dict that json.dumps accepts. Scores are
        rounded to two decimals, and optional fields appear only when set."""
        data = {
            "sentence": self.sentence,
            "clarity_score": round(self.clarity_score, 2),
            "semantic_ambiguity": round(self.semantic_ambiguity, 2),
            "specificity": round(self.specificity, 2),
            "word_count": self.word_count,
            "avg_word_senses": round(self.lexical.avg_senses, 2),
            "avg_wordnet_depth": round(self.lexical.avg_depth, 2),
            "syntax_ambiguity_hits": [
                {"kind": hit.kind, "span": hit.span} for hit in self.syntax.hits
            ],
            "vague_word_hits": [
                {"phrase": hit.phrase, "penalty": hit.penalty} for hit in self.vague_hits
            ],
        }
        # Add optional fields only when present
        if self.readability_score is not None:
            data["readability_score"] = round(self.readability_score, 2)
        if self.context_coherence is not None:
            data["context_coherence"] = round(self.context_coherence, 2)
        if self.structural_clarity is not None:
            data["structural_clarity"] = round(self.structural_clarity, 2)
        return data

    def to_json(self) -> dict:
        """Return the same dict as to_dict(). Kept for compatibility; new
        code should call to_dict()."""
        return self.to_dict()


def analyze(
    sentence: str,
    *,
    weights: ScoreWeights | None = None,
    semantic_scorer: SemanticScorer | None = None,
    extra_vague_words: str | Iterable[str] | None = None,
    include_readability: bool = False,
    coherence_scorer: CoherenceScorer | None = None,
) -> AnalysisResult:
    """Analyze a sentence's clarity with optional additional signals.

    The text is converted to Unicode NFC form, and typographic apostrophes,
    double quotes and hyphens are read as their ASCII forms before scoring.
    AnalysisResult.sentence keeps the text as given.

    Args:
        sentence: The sentence to analyze
        weights: Custom score weights. The defaults add up to 0.80, and the
            formula divides by the sum of the weights of the present signals.
        semantic_scorer: Semantic scorer for polysemy analysis. Defaults to
            WordnetPolysemyScorer.
        extra_vague_words: Additional vague words to check against. A single
            string counts as one entry. Entries are normalized like the text.
        include_readability: Whether to compute readability_score. It changes
            clarity_score only when weights.readability is above 0, which it
            is not by default.
        coherence_scorer: Scorer that computes context_coherence. When it is
            None, no coherence is computed and no model is loaded. The value
            changes clarity_score only when weights.coherence is above 0,
            which it is not by default.

    Returns:
        AnalysisResult with clarity score and all applicable sub-scores.
        Text with no word of two or more letters, such as '', '!!!' or '42',
        scores 0.0 and has a word_count of 0.

    Raises:
        TypeError: If sentence is not a str, for example bytes or None.
    """
    if not isinstance(sentence, str):
        raise TypeError(f"text must be str, not {type(sentence).__name__}")
    weights = weights or ScoreWeights()
    semantic_scorer = semantic_scorer or WordnetPolysemyScorer()

    # Every signal reads the normalized text; the result keeps the original.
    text = _normalize_text(sentence)
    tagged = tag_sentence(text)
    # Filter to alpha tokens that are at least 2 chars long
    # (single letters like 'a', 'A', 'I' are not useful for polysemy analysis).
    # Vague phrases are matched over every token instead, see _vague_tokens.
    words = [token for token, _tag in tagged if len(token) >= 2 and token.isalpha()]

    syntax_report = analyze_syntax(tagged)
    lexical_report = analyze_lexical(words)
    if isinstance(extra_vague_words, str):
        extra_vague_words = [extra_vague_words]
    # Extra entries are normalized like the text, so they match the same words.
    extra = [_normalize_text(word) for word in extra_vague_words or ()]
    vague_hits = find_vague_hits(_vague_tokens(tagged), extra_vague_words=extra)

    # Compute readability if requested (always available — no feature check needed)
    readability_score = None
    if include_readability:
        from .readability import text_to_clarity_score as _rto
        readability_score = _rto(text)

    # Compute coherence if scorer provided (requires semantic-coherence feature)
    context_coherence = None
    if coherence_scorer is not None:
        try:
            context_coherence = coherence_scorer.score(text, tagged)
        except ImportError:
            # Graceful degradation — leave as None
            pass

    # Structure measures markdown layout, so it is computed only for text with
    # more than one line. A single line leaves it None and its weight goes to
    # the other signals.
    structural_clarity = None
    if "\n" in text.strip():
        from .structure import analyze_structure as _analyze_structure
        structural_clarity = _analyze_structure(text).structural_clarity

    if not words:
        empty_lexical = LexicalReport()
        return AnalysisResult(
            sentence=sentence,
            clarity_score=0.0,
            semantic_ambiguity=0.0,
            specificity=0.0,
            readability_score=readability_score,
            context_coherence=context_coherence,
            structural_clarity=structural_clarity,
            syntax=syntax_report,
            lexical=empty_lexical,
            vague_hits=vague_hits,
            weights=weights,
        )

    semantic_ambiguity = min(100.0, max(0.0, semantic_scorer.score(text, words)))

    # Normalize vague penalty: cap it so it doesn't overwhelm the base specificity.
    # Use unique hit phrases to avoid double-counting repeated vague words,
    # and scale as a percentage of total word count (max 40% deduction).
    unique_vague = set(h.phrase.lower() for h in vague_hits)
    vague_ratio = min(len(unique_vague) / max(len(set(w.lower() for w in words)), 1), 1.0)
    vague_penalty = vague_ratio * 40  # Max 40% deduction from unique vague word ratio

    base_specificity = min(lexical_report.avg_depth / 15.0 * 100, 100)
    specificity = max(0.0, min(base_specificity - vague_penalty, 100.0))
    vagueness = 100 - specificity

    # Normalize syntax penalty: count hits per sentence so long documents
    # don't get penalized disproportionately. Cap at 10 (a reasonable max).
    sentence_count = max(1, len(re.findall(r'[.!?]+', text)))
    hit_rate_per_sentence = syntax_report.ambiguity_score / sentence_count
    syntax_penalty = min(hit_rate_per_sentence * 25, 10)

    # ===== WEIGHTED FORMULA WITH REDISTRIBUTION =====
    final_ambiguity = _compute_weighted_ambiguity(
        semantic_ambiguity=semantic_ambiguity,
        vagueness=vagueness,
        syntax_penalty=syntax_penalty,
        readability_score=readability_score,
        coherence_score=context_coherence,
        structural_clarity=structural_clarity,
        weights=weights,
    )

    final_ambiguity = max(0.0, min(final_ambiguity, 100.0))
    clarity_score = 100 - final_ambiguity

    return AnalysisResult(
        sentence=sentence,
        clarity_score=clarity_score,
        semantic_ambiguity=semantic_ambiguity,
        specificity=specificity,
        readability_score=readability_score,
        context_coherence=context_coherence,
        structural_clarity=structural_clarity,
        syntax=syntax_report,
        lexical=lexical_report,
        vague_hits=vague_hits,
        weights=weights,
    )


def _compute_weighted_ambiguity(
    semantic_ambiguity: float,
    vagueness: float,
    syntax_penalty: float,
    readability_score: Optional[float],
    coherence_score: Optional[float],
    structural_clarity: Optional[float],
    weights: ScoreWeights,
) -> float:
    """Compute weighted ambiguity score with automatic weight redistribution.

    When some signals are absent (None or 0 weight), remaining signals absorb
    their weight proportionally so the formula always sums to a valid score.

    Note: readability_score, coherence_score, and structural_clarity are already
    on 0-100 clarity scale where higher = better. Vagueness, syntax_penalty,
    and semantic_ambiguity are on 0-100 ambiguity scale where higher = worse.

    For the formula, we invert clarity signals to the ambiguity scale:
        ambiguity_from_readability = 100 - readability_score
        ambiguity_from_coherence = 100 - coherence_score
        ambiguity_from_structure = 100 - structural_clarity
    """
    # Build list of (ambiguity_value, weight) for enabled signals
    total_weight = 0.0

    if weights.semantic > 0:
        total_weight += weights.semantic
    if weights.vagueness > 0:
        total_weight += weights.vagueness
    if weights.syntax > 0:
        total_weight += weights.syntax
    if readability_score is not None and weights.readability > 0:
        total_weight += weights.readability
    if coherence_score is not None and weights.coherence > 0:
        total_weight += weights.coherence
    if structural_clarity is not None and weights.structure > 0:
        total_weight += weights.structure

    if total_weight == 0:
        # Fallback: unweighted average of available signals
        values = [semantic_ambiguity, vagueness, syntax_penalty]
        if readability_score is not None:
            values.append(100.0 - readability_score)
        if coherence_score is not None:
            values.append(100.0 - coherence_score)
        if structural_clarity is not None:
            values.append(100.0 - structural_clarity)
        return max(0.0, min(sum(values) / max(len(values), 1), 100.0))

    weighted_sum = (
        semantic_ambiguity * weights.semantic
        + vagueness * weights.vagueness
        + syntax_penalty * weights.syntax
    )

    if readability_score is not None and weights.readability > 0:
        # Invert: high readability -> low ambiguity contribution
        weighted_sum += (100.0 - readability_score) * weights.readability

    if coherence_score is not None and weights.coherence > 0:
        # Invert: high coherence -> low ambiguity contribution
        weighted_sum += (100.0 - coherence_score) * weights.coherence

    if structural_clarity is not None and weights.structure > 0:
        # Invert: high structural clarity -> low ambiguity contribution
        weighted_sum += (100.0 - structural_clarity) * weights.structure

    return weighted_sum / total_weight

__all__ = [
    "AnalysisResult",
    "ScoreWeights",
    "analyze",
]
