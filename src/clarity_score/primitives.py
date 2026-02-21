"""Core signal extraction — computes every sub-score ONCE so that formula
combinations can be applied later without re-scoring.

This module is the "compute primitives once, apply many formulas" core of the
clarity scoring system.  Each call to ``extract_primitives()`` returns a
frozen :class:`ClarityPrimitives` dataclass containing all raw sub-scores on
a 0–100 scale.  The user can then create multiple ``FormulaWeights`` objects,
call ``apply_formula(prims, weights)`` for each one, and get back the full
set of clarity scores without ever re-touching the document text.

Default signal names (all on 0-100 where **higher = worse/ambiguous**):

    semantic_ambiguity    Word polysemy → higher means more ambiguous words
    vagueness             Placeholder-word ratio + low wordnet depth penalty
    syntax_penalty        POS-pattern ambiguity hits (capped)
    structure_ambiguity   Inverted structural clarity: 100 - struct_score

Clarity signals (all on 0-100 where **higher = better**):

    readability_score     Flesch-Kincaid / Gunning Fog / SMOG composite
    coherence             Embedding similarity (feature-gated, needs scorer)

The default ``analyze()`` function in ``scoring.py`` internally computes these
same primitives and then applies a weighted sum.  This module exposes the
primitives directly so they can be cached, exported to JSONL, or recombined.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from typing import Optional
from pathlib import Path


# ---------------------------------------------------------------------------
# Data class: all sub-scores in one place
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClarityPrimitives:
    """All raw clarity signals for a single document version.

    All numeric fields are on a 0-100 scale unless noted.  Ambiguity-weighted
    signals have **higher = worse** (more ambiguous); clarity-weighted signals
    have **higher = better**.
    """
    semantic_ambiguity: float          # 0-100, higher=more ambiguous
    specificity: float                 # 0-100, higher=more specific
    vagueness: float                   # 0-100 (= 100 - specificity)
    syntax_penalty: float              # 0-10 (capped at 10), higher=more ambiguous
    readability_score: Optional[float] # 0-100, higher=easier to read; None if disabled
    coherence: Optional[float]         # 0-100, higher=better flow; None if disabled
    structural_clarity: Optional[float]# 0-100, higher=well-structured; None for single-line text

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @staticmethod
    def from_dict(d: dict) -> "ClarityPrimitives":
        """Build primitives from a dict, ignoring keys that are not fields.

        The four float fields are required.  A missing optional field
        (readability_score, coherence or structural_clarity) becomes None.
        """
        return ClarityPrimitives(
            semantic_ambiguity=d["semantic_ambiguity"],
            specificity=d["specificity"],
            vagueness=d["vagueness"],
            syntax_penalty=d["syntax_penalty"],
            readability_score=d.get("readability_score"),
            coherence=d.get("coherence"),
            structural_clarity=d.get("structural_clarity"),
        )


# ---------------------------------------------------------------------------
# Formula weights — defines how to combine primitives into a clarity score
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FormulaWeights:
    """Defines a specific weighting combination for computing clarity.

    Unlike :class:`~clarity_score.scoring.ScoreWeights` (which controls the
    internal ``analyze()`` pipeline), this class is lightweight: it just maps
    signal names to weights.  ``apply_formula()`` combines them with the same
    rule as ``analyze()``, so equal weights give equal scores.

    Signal names:
        semantic, vagueness, syntax, readability, coherence, structure

    Inversion:
        ``apply_formula()`` turns the clarity scale signals (readability,
        coherence, structure) into ambiguity as 100 minus the signal before
        weighting them.
    """
    semantic: float = 0.24
    vagueness: float = 0.24
    syntax: float = 0.12
    readability: float = 0.0      # set >0 to include
    coherence: float = 0.0        # same (requires primitives.coherence is not None)
    structure: float = 0.20       # set to 0 to leave structure out

    def enabled_weight_sum(self) -> float:
        """Sum of all non-zero weights (for normalization)."""
        return sum(w for w in [self.semantic, self.vagueness, self.syntax,
                               self.readability, self.coherence, self.structure] if w > 0.0)


# ---------------------------------------------------------------------------
# Predefined formula presets — 5 grid-search configurations
# ---------------------------------------------------------------------------

# These are the formulas we want to benchmark across every skill/commit:
DEFAULT_WEIGHTS = FormulaWeights()          # current default (structure+semantic+vague)
READABILITY_ENABLED_WEIGHTS = FormulaWeights(readability=0.30, structure=0.20)  # add readability
NO_STRUCTURE_WEIGHTS = FormulaWeights(semantic=0.30, vagueness=0.30, syntax=0.15, readability=0.25, structure=0.0)  # no structure, evenly-ish
VAGUENESS_HEAVY_WEIGHTS = FormulaWeights(semantic=0.35, vagueness=0.40, syntax=0.10, readability=0.15, structure=0.0)  # heavy vague/semantic
EVEN_DISTRIBUTION_WEIGHTS = FormulaWeights(semantic=0.125, vagueness=0.125, syntax=0.125, readability=0.15, coherence=0.15, structure=0.25)  # evenly-ish


def _prism_weights() -> list[tuple[str, FormulaWeights]]:
    """Return the default grid of formula names → weights for benchmarking."""
    return [
        ("default", DEFAULT_WEIGHTS),
        ("readability_enabled", READABILITY_ENABLED_WEIGHTS),
        ("no_structure", NO_STRUCTURE_WEIGHTS),
        ("vagueness_heavy", VAGUENESS_HEAVY_WEIGHTS),
        ("even_distribution", EVEN_DISTRIBUTION_WEIGHTS),
    ]


# ---------------------------------------------------------------------------
# Public API — single-pass extraction + formula application
# ---------------------------------------------------------------------------

def extract_primitives(
    text: str,
    include_readability: bool = True,
    include_coherence: bool = False,
    coherence_scorer=None,  # Any object with .score(text, tagged) → float
) -> ClarityPrimitives:
    """Compute ALL raw clarity signals for *text* in a single pass.

    This function replaces the old ``analyze()`` entry point when you want to
    score many formulas over the same text (e.g. during grid-search tuning).

    Returns a frozen :class:`ClarityPrimitives` dataclass containing every
    sub-score on a 0-100 scale (ambiguity-weighted for bad signals, clarity-
    weighted for good ones).

    Args:
        text: The document text to analyze.
        include_readability: Compute Flesch-Kincaid / Gunning Fog metrics?
        include_coherence: Use an embedding scorer for semantic flow?
        coherence_scorer: Required if ``include_coherence=True`` — must have
            a ``score(text, tagged_tokens) -> float`` method.

    Returns:
        ClarityPrimitives with all sub-scores populated (or None for disabled
        signals).
    """
    from .lexical import analyze_lexical
    from .scorer import WordnetPolysemyScorer
    from .scoring import _vague_tokens
    from .syntax import analyze_syntax, tag_sentence
    from .vague_lexicon import find_vague_hits
    from .structure import analyze_structure as _analyze_structure

    semantic_scorer = WordnetPolysemyScorer()
    tagged = tag_sentence(text)
    words = [token for token, _tag in tagged if len(token) >= 2 and token.isalpha()]

    # 1. Semantic ambiguity (word polysemy)
    semantic_ambiguity = semantic_scorer.score(text, words) if words else 0.0

    # 2. Vagueness (specificity from wordnet depth + vague hit penalty)
    lexical_report = analyze_lexical(words)
    vague_hits = find_vague_hits(_vague_tokens(tagged))

    unique_vague = set(h.phrase.lower() for h in vague_hits)
    vague_ratio = min(len(unique_vague) / max(len(set(w.lower() for w in words)), 1), 1.0)
    vague_penalty = vague_ratio * 40
    base_specificity = min(lexical_report.avg_depth / 15.0 * 100, 100)
    specificity = max(0.0, min(base_specificity - vague_penalty, 100.0))
    vagueness = 100.0 - specificity

    # 3. Syntax penalty (POS-pattern ambiguity hits, capped)
    syntax_report = analyze_syntax(tagged)
    sentence_count = max(1, len(re.findall(r'[.!?]+', text)))
    hit_rate_per_sentence = syntax_report.ambiguity_score / sentence_count
    syntax_penalty = min(hit_rate_per_sentence * 25, 10)

    # 4. Readability (optional — Flesch-Kincaid composite)
    readability_score = None
    if include_readability:
        from .readability import text_to_clarity_score as _rto
        readability_score = _rto(text)

    # 5. Structural clarity (only for text with more than one line, as in analyze())
    structural_clarity = None
    if "\n" in text.strip():
        structural_clarity = _analyze_structure(text).structural_clarity

    # 6. Coherence (feature-gated — embedding-based, optional)
    coherence_val = None
    if include_coherence and coherence_scorer is not None:
        try:
            coherence_val = coherence_scorer.score(text, tagged)
        except ImportError:
            pass

    return ClarityPrimitives(
        semantic_ambiguity=round(semantic_ambiguity, 4),
        specificity=round(specificity, 4),
        vagueness=round(vagueness, 4),
        syntax_penalty=round(syntax_penalty, 4),
        readability_score=round(readability_score, 2) if readability_score is not None else None,
        coherence=round(coherence_val, 2) if coherence_val is not None else None,
        structural_clarity=round(structural_clarity, 2) if structural_clarity is not None else None,
    )


def apply_formula(
    prim: ClarityPrimitives,
    weights: FormulaWeights,
) -> float:
    """Apply a weighted formula to pre-computed primitives → clarity score.

    The ambiguity scale signals (semantic, vagueness, syntax) are kept as-is;
    the clarity scale signals (readability, coherence, structure) are inverted
    to the ambiguity scale before weighting.  As in ``analyze()``, the sum is
    divided by the weights above 0 of the signals that are present, so the
    weight of a signal that is None goes to the others.

    Returns:
        Clarity score in [0, 100], where higher = more clear.
    """
    w = weights
    total_weight = sum(x for x in (w.semantic, w.vagueness, w.syntax) if x > 0.0)
    if prim.readability_score is not None and w.readability > 0:
        total_weight += w.readability
    if prim.coherence is not None and w.coherence > 0:
        total_weight += w.coherence
    if prim.structural_clarity is not None and w.structure > 0:
        total_weight += w.structure

    if total_weight == 0:
        # Unweighted average of all available signals
        values = [prim.semantic_ambiguity, prim.vagueness, prim.syntax_penalty]
        if prim.readability_score is not None:
            values.append(100.0 - prim.readability_score)
        if prim.coherence is not None:
            values.append(100.0 - prim.coherence)
        if prim.structural_clarity is not None:
            values.append(100.0 - prim.structural_clarity)
        return 100.0 - (sum(values) / max(len(values), 1))

    weighted_sum = (
        prim.semantic_ambiguity * w.semantic
        + prim.vagueness * w.vagueness
        + prim.syntax_penalty * w.syntax
    )

    if prim.readability_score is not None and w.readability > 0:
        weighted_sum += (100.0 - prim.readability_score) * w.readability

    if prim.coherence is not None and w.coherence > 0:
        weighted_sum += (100.0 - prim.coherence) * w.coherence

    if prim.structural_clarity is not None and w.structure > 0:
        weighted_sum += (100.0 - prim.structural_clarity) * w.structure

    final_ambiguity = weighted_sum / total_weight
    return round(100.0 - max(0.0, min(final_ambiguity, 100.0)), 2)


def apply_all_formulas(
    prim: ClarityPrimitives,
    formula_names_and_weights=None,
) -> dict[str, float]:
    """Apply a suite of formula configurations to one set of primitives.

    Returns a dict mapping formula name → clarity score (0-100).
    """
    formulas = formula_names_and_weights or _prism_weights()
    return {name: apply_formula(prim, fw) for name, fw in formulas}


# ---------------------------------------------------------------------------
# JSONL export / import helpers
# ---------------------------------------------------------------------------

def save_primitives(path: Path, rows: list[dict], fmt: str = "jsonl") -> None:
    """Save a list of row dicts to a JSONL file, one row per line.

    Each row is a dict with keys:
        - commit_hash (str)
        - metadata  (optional arbitrary dict, such as author and message)
        - primitives (ClarityPrimitives or dict)

    Output format per line::

        {"commit_hash":"abc123","metadata":{"author":"Jane Doe","msg":"Add skill X"},
         "primitives":{"semantic_ambiguity":55.0,"specificity":30.0,...}}
    """
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            line = dict(row)
            prims = row["primitives"]
            if isinstance(prims, ClarityPrimitives):
                line["primitives"] = prims.to_dict()
            f.write(json.dumps(line) + "\n")


def load_primitives(path: Path) -> list[dict]:
    """Load primitives from a JSONL file produced by ``save_primitives``.

    Keys in ``primitives`` that are not ClarityPrimitives fields are ignored,
    so a file written by a newer version still loads.
    """
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            row = json.loads(line)
            prims = row.get("primitives")
            if isinstance(prims, dict):
                row["primitives"] = ClarityPrimitives.from_dict(prims)
            rows.append(row)
    return rows

__all__ = [
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
