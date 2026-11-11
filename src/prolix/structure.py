"""Structural clarity analysis for markdown documents.

Measures how well-structured a document is — an orthogonal dimension to
semantic/lexical signals.  A document can be semantically clear but poorly
structured (hard to follow), or conversely, well-structured with vague content.

This signal captures four dimensions:

1. **Heading hierarchy** — proper use of H2-H4 section headers
2. **List density** — bullet points and numbered lists for actionable steps  
3. **Example presence** — code blocks, inline code examples, concrete samples
4. **Action verb ratio** — imperative sentences vs descriptive prose

All formulas are implemented from scratch; no vendored dependencies.

Usage::

    from prolix.structure import analyze_structure
    result = analyze_structure("Some markdown text")
    print(f"structural_clarity: {result.structural_clarity:.1f}/100")
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StructureReport:
    """Summary of structural analysis results."""

    heading_count: int = 0
    list_item_count: int = 0
    code_block_count: int = 0
    action_verb_ratio: float = 0.5
    paragraph_count: int = 0
    max_heading_depth: int = 0
    structural_clarity: float = 50.0  # Overall score [10, 100]

    @property
    def heading_density(self) -> float:
        """Headings per 100 lines (normalized)."""
        return self.heading_count / max(self._line_count(), 1) * 100

    @property
    def list_density(self) -> float:
        """List items per 100 lines (normalized)."""
        return self.list_item_count / max(self._line_count(), 1) * 100

    @property
    def example_ratio(self) -> float:
        """Ratio of lines with examples (code blocks or inline code) to total lines."""
        if not self.code_block_count:
            return 0.0
        # Approximate: each code block spans ~5-10 lines; count by presence
        return min(1.0, self.code_block_count * 2 / max(self._line_count(), 1))

    def _line_count(self) -> int:
        return max(1, self.heading_count + self.list_item_count + self.paragraph_count)


# ---------------------------------------------------------------------------
# Heading analysis
# ---------------------------------------------------------------------------

# Horizontal whitespace only, so no match can cross a line and the scan stays
# linear on long runs of blank lines or spaces.
_HEADINGS_RE = re.compile(r"^(#{1,6})[ \t]+(\S.*)$", re.MULTILINE)


def _count_headings(text: str) -> int:
    """Count valid markdown headings (# through ######)."""
    return len(_HEADINGS_RE.findall(text))


def _max_heading_depth(text: str) -> int:
    """Return the depth (1-6) of the deepest heading."""
    matches = _HEADINGS_RE.findall(text)
    if not matches:
        return 0
    return max(len(h[0]) for h in matches)


# ---------------------------------------------------------------------------
# List analysis
# ---------------------------------------------------------------------------

_UNORDERED_LIST = re.compile(r"^[ \t]*[-*\u2022][ \t]+\S", re.MULTILINE)
_ORDERED_LIST = re.compile(r"^[ \t]*\d+[.)][ \t]+\S", re.MULTILINE)


def _count_list_items(text: str) -> int:
    """Count bullet points and numbered list items."""
    return len(_UNORDERED_LIST.findall(text)) + len(_ORDERED_LIST.findall(text))


# ---------------------------------------------------------------------------
# Example/code block analysis
# ---------------------------------------------------------------------------

_CODE_BLOCK = re.compile(r"^(\s*)```(\w+)?\\n", re.MULTILINE)
_INLINE_CODE = re.compile(r"`[^`]+`")


def _count_code_blocks(text: str) -> int:
    """Count fenced code blocks by counting opening ``` with optional language tag.
    
    We only count lines that have ``` followed by a word (language spec)
    or are bare ``` at the start of a non-empty line. Closing ``` lines
    are bare and on their own — we skip them to avoid double-counting.
    """
    count = 0
    in_block = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_block:
                # Opening fence — count it
                count += 1
                in_block = True
            else:
                # Closing fence — just flip flag, don't count
                in_block = False
    return count


def _strip_fenced_blocks(text: str) -> str:
    """Remove fenced code blocks, fence lines included.

    Uses the same fence rule as ``_count_code_blocks``, so a block that is
    never closed runs to the end of the text.  Comment lines such as
    ``# install`` inside a fence are then not counted as headings.
    """
    kept: list[str] = []
    in_block = False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_block = not in_block
        elif not in_block:
            kept.append(line)
    return "\n".join(kept)


# ---------------------------------------------------------------------------
# Action verb analysis
# ---------------------------------------------------------------------------

# Imperative/action verb patterns at the start of sentences
_ACTION_VERBS = {
    "create", "delete", "update", "add", "remove", "insert", "append",
    "set", "configure", "install", "setup", "build", "deploy", "test",
    "run", "execute", "call", "invoke", "pass", "specify", "define",
    "include", "exclude", "avoid", "use", "follow", "check", "verify",
    "ensure", "provide", "return", "validate", "parse", "render",
    "generate", "format", "transform", "apply", "enable", "disable",
    "click", "open", "select", "type", "enter", "press", "go", "choose",
    "navigate", "save", "close", "copy", "paste", "rename", "move", "sort",
    "download", "upload", "fix", "find", "show", "list",
}

_SENTENCE_BOUNDARY = re.compile(r"[.!?]\s+[A-Z]")


def _estimate_action_ratio(text: str) -> float:
    """Estimate the ratio of action-oriented vs descriptive sentences.

    Counts sentences that begin with an action verb as a heuristic for
    imperative instruction density.  Returns value in [0, 1].
    """
    # Split into sentences (naive but effective for this purpose)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if not sentences:
        return 0.5

    action_count = 0
    for sentence in sentences:
        stripped = sentence.strip()
        if len(stripped) < 10:
            continue  # Skip very short fragments
        first_word = re.split(r"\s+", stripped.lower())[0]
        # Strip trailing punctuation from first word
        first_word = re.sub(r"[^\w]", "", first_word)
        if first_word in _ACTION_VERBS:
            action_count += 1

    return min(1.0, action_count / max(len(sentences), 1))


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------


def analyze_structure(text: str) -> StructureReport:
    """Analyze the structural clarity of a markdown document.

    structural_clarity is the sum of four parts and a bonus, clamped to
    10 to 100:
        - Headings: headings per 100 lines, up to 30 points
        - Lists: list items per 100 lines, up to 30 points
        - Code examples: 5 points per fenced code block, up to 20 points
        - Action verbs: 30 times the share of sentences that start with a
          listed action verb, up to 30 points
        - Heading depth bonus: 5 points when the deepest heading is level 2 to 4

    A document shorter than 100 lines counts as 100 lines, so each heading
    and each list item is worth one point there. Headings, list items and
    sentences inside fenced code blocks are not counted.

    Args:
        text: Markdown text to analyze

    Returns:
        StructureReport with structural_clarity score [10, 100]
    """
    # Headings, lists and sentences inside fenced code are not document structure.
    prose = _strip_fenced_blocks(text)
    heading_count = _count_headings(prose)
    list_items = _count_list_items(prose)
    code_blocks = _count_code_blocks(text)
    action_ratio = _estimate_action_ratio(prose)
    max_depth = _max_heading_depth(prose)

    # Calculate density metrics (per 100 lines)
    lines = text.split("\n") if text else [""]
    line_count = len(lines)

    heading_density_score = min(30, heading_count / max(line_count / 100, 1))
    list_density_score = min(30, list_items / max(line_count / 100, 1))
    
    # Example score: presence of code blocks boosts clarity significantly
    example_score = min(20, code_blocks * 5)
    
    # Action ratio: higher = more imperative/instructional = clearer for skills
    action_score = action_ratio * 30

    # Sum of the parts (30, 30, 20 and 30 points at most)
    raw_clarity = heading_density_score + list_density_score + example_score + action_score
    
    # Add structural bonus for good heading depth (H2-H4 ideal for skills)
    if max_depth >= 2 and max_depth <= 4:
        raw_clarity += 5

    # Clamp to [10, 100]
    structural_clarity = max(10.0, min(100.0, raw_clarity))

    return StructureReport(
        heading_count=heading_count,
        list_item_count=list_items,
        code_block_count=code_blocks,
        action_verb_ratio=action_ratio,
        paragraph_count=len(re.findall(r"\n\s*\n", text)),
        max_heading_depth=max_depth,
        structural_clarity=round(structural_clarity, 2),
    )

__all__ = [
    "StructureReport",
    "analyze_structure",
]
