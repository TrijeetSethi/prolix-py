"""Readability scoring via standard formulas (Flesch-Kincaid, Gunning Fog, SMOG).

All formulas reimplemented from scratch. No vendored code from textstat or any other project.

Formulas implemented:
    - Flesch Reading Ease (FRE)
    - Flesch-Kincaid Grade Level (FKG)
    - Gunning Fog Index (GFI)
    - SMOG Index
    - Automated Readability Index (ARI)
    - Coleman-Liau Index (CLI)

Not implemented (out of scope for clarity scoring):
    - Dale-Chall (would need large word list, not worth the data dependency)
    - Linsear Write (less established than GFI)
    - International variants (we only analyze English text)

Reference formulas:
    FRE  = 206.835 - 1.015*(words/sentences) - 84.6*(syllables/words)
    FKG  = 0.39*(words/sentences) + 11.8*(syllables/words) - 15.59
    GFI  = 0.4*((words/sentences) + 100*(polysyllabic/words))
    SMOG = 1.043*sqrt(30*(polysyllabic/sentences)) + 3.1291
    ARI  = 4.71*(chars/words) + 0.5*(words/sentences) - 21.43
    CLI  = 0.0588*(letters/words)*100 - 0.296*(sentences/words)*100 - 15.8
"""

from __future__ import annotations

import math
import re


class ReadabilityMetrics:
    """Results from readability analysis. Mirrors a Rust-like struct."""

    def __init__(
        self,
        flesch_reading_ease: float,
        flesch_kincaid_grade: float,
        gunning_fog_index: float,
        smog_index: float,
        automated_readability: float,
        coleman_liau_index: float,
    ):
        self.flesch_reading_ease = flesch_reading_ease
        self.flesch_kincaid_grade = flesch_kincaid_grade
        self.gunning_fog_index = gunning_fog_index
        self.smog_index = smog_index
        self.automated_readability = automated_readability
        self.coleman_liau_index = coleman_liau_index

    def to_clarity_score(self) -> float:
        """Convert FRE (0-100, higher=easier) to clarity score (0-100, higher=clearer).

        Mapping:
            clarity = 25 + 75 * sqrt(FRE / 100), with FRE clamped to 0 to 100

        So FRE 0 gives 25, FRE 25 gives 62.5 and FRE 100 gives 100. The
        square root rewards easy text more than a linear map would, because
        readability matters disproportionately for skill documentation. The
        floor of 25 reflects that complex text can still be unambiguous,
        which the other signals measure.
        """
        fre = max(0.0, self.flesch_reading_ease)
        clarity = 25.0 + math.sqrt(fre / 100.0) * 75.0
        return min(100.0, max(25.0, clarity))


# ============================================================
# Counting helpers
# ============================================================

_SENTENCE_TERMINATORS_RE = re.compile(r'[.!?]+')


def count_sentences(text: str) -> int:
    """Count sentence boundaries (. ! ?)."""
    sentences = _SENTENCE_TERMINATORS_RE.split(text)
    non_empty = [s.strip() for s in sentences if s.strip()]
    if not non_empty:
        return 0
    # Default to 1 if no terminators found but text is present
    return max(1, len(non_empty))


_WORDS_RE = re.compile(r"[a-zA-Z]+(?:'[a-z]+)?")


def count_words(text: str) -> list[str]:
    """Extract alphabetic words (handles contractions)."""
    return _WORDS_RE.findall(text)


def count_syllables(word: str) -> int:
    """Estimate syllable count using vowel-group heuristic.

    Algorithm (English):
        1. Lowercase the word
        2. Handle contractions by splitting on apostrophe into parts
        3. Remove trailing silent 'e' from each part (except final 'le')
        4. Count contiguous vowel groups in each part
        5. Clamp between 1 and min(word_length, 7)

    This is a heuristic with ~85% accuracy vs dictionary lookup.
    It is independent of textstat's implementation which uses CMU dict + Pyphen.

    Accuracy limitations:
        - Complex consonant clusters approximated
        - Y as vowel at special positions not perfectly handled
        - Silent 'le' endings handled but edge cases exist

    For clarity-score purposes, relative ordering matters more than
    absolute accuracy — we care whether this sentence is harder to read
    than that one, not whether the syllable count is exactly correct.
    """
    word = word.lower().strip()
    if not word:
        return 0

    vowels = set('aeiouy')

    # Handle contractions: split on apostrophe and process each part
    parts = word.split("'")
    total = 0
    for i, part in enumerate(parts):
        if not part:
            continue
        w = part
        # Remove trailing silent 'e' (not in 'le' endings)
        if len(w) >= 2 and w[-1] == 'e' and w[-2] != 'l':
            w = w[:-1]
        # Count vowel groups in this part
        count = 0
        prev_is_vowel = False
        for char in w:
            is_vowel = char in vowels
            if is_vowel and not prev_is_vowel:
                count += 1
            prev_is_vowel = is_vowel
        # Contraction suffix heuristic: short parts after apostrophe (like 't, 're, 've) count as syllables
        if i > 0 and len(part) <= 2 and count == 0:
            count = 1
        total += count

    if total == 0:
        # Fallback: check original for any vowel
        if any(c in vowels for c in word):
            return 1
        return 0

    # Clamp between 1 and min(total_possible, 7)
    return max(1, min(total, len(word), 7))


def count_syllables_in_text(text: str) -> int:
    """Count total syllables in text."""
    words = count_words(text)
    return sum(count_syllables(w) for w in words)


def count_polysyllabic_words(text: str) -> int:
    """Count words with 3+ syllables (used by SMOG, Gunning Fog)."""
    words = count_words(text)
    return sum(1 for w in words if count_syllables(w) >= 3)


def count_chars_excluding_spaces(text: str) -> int:
    """Count non-whitespace characters (used by ARI)."""
    return len(re.sub(r'\s', '', text))


# ============================================================
# Formula implementations
# ============================================================


def flesch_reading_ease(sentences: float, words: float, syllables: float) -> float:
    """Flesch Reading Ease: 206.835 - 1.015*(words/sentences) - 84.6*(syllables/words)."""
    if words == 0 or sentences == 0:
        return 0.0
    asl = words / sentences       # Average Sentence Length
    asw = syllables / words       # Average Syllables per Word
    return max(0.0, min(100.0, 206.835 - 1.015 * asl - 84.6 * asw))


def flesch_kincaid_grade(sentences: float, words: float, syllables: float) -> float:
    """Flesch-Kincaid Grade Level: 0.39*(words/sentences) + 11.8*(syllables/words) - 15.59."""
    if words == 0 or sentences == 0:
        return 0.0
    asl = words / sentences
    asw = syllables / words
    return 0.39 * asl + 11.8 * asw - 15.59


def gunning_fog_index(sentences: float, words: float, polysyllabic: int) -> float:
    """Gunning Fog Index: 0.4 * ((words/sentences) + 100*(polysyllabic/words))."""
    if words == 0 or sentences == 0:
        return 0.0
    asl = words / sentences
    pct_poly = polysyllabic / words
    return max(0.0, 0.4 * (asl + 100.0 * pct_poly))


def smog_index(sentences: float, polysyllabic: int) -> float:
    """SMOG Index: 1.043 * sqrt(30 * (polysyllabic/sentences)) + 3.1291."""
    if sentences == 0:
        return 0.0
    polys_per_30 = 30.0 * polysyllabic / sentences
    return 1.043 * math.sqrt(polys_per_30) + 3.1291


def automated_readability(sentences: float, words: float, chars: float) -> float:
    """Automated Readability Index: 4.71*(chars/words) + 0.5*(words/sentences) - 21.43."""
    if words == 0 or sentences == 0:
        return 0.0
    asw = words / sentences
    cpw = chars / words
    return max(0.0, 4.71 * cpw + 0.5 * asw - 21.43)


def coleman_liau(sentences: float, words: float, chars: float) -> float:
    """Coleman-Liau Index: 0.0588*(letters/words)*100 - 0.296*(sentences/words)*100 - 15.8.

    ``chars`` is the number of letters, not counting digits or punctuation.
    """
    if words == 0:
        return 0.0
    letters = (chars / words) * 100.0  # letters per 100 words
    s = (sentences / words) * 100.0    # sentences per 100 words
    return 0.0588 * letters - 0.296 * s - 15.8


# ============================================================
# Public API
# ============================================================


def compute_readability_metrics(text: str) -> ReadabilityMetrics:
    """Compute all readability metrics for a text string."""
    sentences = count_sentences(text)
    words = count_words(text)
    words_f = len(words)
    syllables = count_syllables_in_text(text)
    polysyllabic = count_polysyllabic_words(text)
    chars = count_chars_excluding_spaces(text)
    letters = sum(1 for c in text if c.isalpha())

    return ReadabilityMetrics(
        flesch_reading_ease=flesch_reading_ease(sentences, words_f, syllables),
        flesch_kincaid_grade=flesch_kincaid_grade(sentences, words_f, syllables),
        gunning_fog_index=gunning_fog_index(sentences, words_f, polysyllabic),
        smog_index=smog_index(sentences, polysyllabic),
        automated_readability=automated_readability(sentences, words_f, chars),
        coleman_liau_index=coleman_liau(sentences, words_f, letters),
    )


def text_to_clarity_score(text: str) -> float:
    """Compute a clarity-aligned readability score for text (convenience wrapper)."""
    metrics = compute_readability_metrics(text)
    return metrics.to_clarity_score()

__all__ = [
    "ReadabilityMetrics",
    "compute_readability_metrics",
    "text_to_clarity_score",
]
