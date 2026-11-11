"""High-level entry point for clarity scoring of skills, documents, and batches.

This module provides a unified ``clarify()`` function that accepts three
input modes:

1. **Single file** – ``clarify("skills/brand/SKILL.md")`` → ``AnalysisResult``
2. **Directory scan** – ``clarify("skills/")`` → ``list[tuple[Path, AnalysisResult]]``
3. **Batch JSONL** – ``clarify("batch.jsonl")`` → ``dict[str, AnalysisResult]``

All three modes funnel through the same internal ``analyze()`` pipeline so
the scoring logic is identical regardless of input shape.

Optional YAML frontmatter (``---`` blocks at the top of SKILL.md files) is
automatically stripped before scoring so only the actual skill instructions
are analysed.

Usage examples::

    # Single file
    from prolix.clarify import clarify
    result = clarify("skills/foo/SKILL.md")
    print(result.clarity_score)

    # Directory scan (recursive, finds all .md files or SKILL.md)
    results = clarify("skills/")
    for path, res in sorted(results):
        print(f"{path}: {res.clarity_score:.1f}")

    # Batch JSONL — one JSON object per line with "path" and optional "content" keys
    results = clarify("batch.jsonl")
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .scorer import CoherenceScorer, SemanticScorer
    from .scoring import ScoreWeights

from .scoring import AnalysisResult, analyze

__all__ = [
    "clarify",
    "compare_models",
]

logger = logging.getLogger(__name__)


def _check_on_error(on_error: str) -> None:
    """Raise ``ValueError`` unless *on_error* is ``"skip"`` or ``"raise"``."""
    if on_error not in ("skip", "raise"):
        raise ValueError(f"on_error must be 'skip' or 'raise', got {on_error!r}")


# ---------------------------------------------------------------------------
# File discovery helpers
# ---------------------------------------------------------------------------


# Front matter opens with a first line that is exactly --- and closes at the
# next line that is exactly ---. Trailing spaces and tabs are allowed on both.
_FRONTMATTER_RE = re.compile(r"---[ \t]*\n(?:.*?\n)?---[ \t]*(?:\n|\Z)", re.DOTALL)


def _strip_frontmatter(text: str) -> str:
    """Strip YAML frontmatter (--- ... ---) from the beginning of *text*.

    SKILL.md files often start with a metadata block::

        ---
        name: my-skill
        description: Does stuff
        license: MIT
        ---

        Actual skill content ...

    Front matter exists only when the first line is exactly ``---``, and it
    ends at the next line that is exactly ``---``. Trailing spaces and tabs on
    those two lines are allowed. A leading byte order mark is ignored and CRLF
    line endings are read as LF. This function returns everything after the
    closing line with leading whitespace removed. If there is no front matter
    the text is returned verbatim.
    """
    normalized = text.removeprefix("\ufeff").replace("\r\n", "\n")
    match = _FRONTMATTER_RE.match(normalized)
    if match is None:
        return text
    return normalized[match.end():].lstrip()


def _discover_single_file(path: Path) -> list[Path]:
    """Return ``[path]`` if it exists and is a file; raise ``FileNotFoundError``."""
    if not path.is_file():
        raise FileNotFoundError(f"Not a file: {path}")
    return [path]


def _discover_directory(path: Path, pattern: str = "**/*.md") -> list[Path]:
    """Recursively find .md files under *path*.

    Args:
        path: Directory to scan.
        pattern: Glob pattern (default ``**/*.md`` finds all markdown files).

    Returns:
        Sorted list of discovered file paths.
    """
    if not path.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")

    files = sorted(path.glob(pattern))
    # Filter to only regular files (not directories that glob might return)
    return [f for f in files if f.is_file()]


def _discover_batch_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL file where each line is ``{"path": "...", "content": "..."}``.

    Supported line shapes:
        {"path": "skills/foo/SKILL.md"}
            reads the content from disk at runtime.
        {"path": "skills/foo/SKILL.md", "content": "# My skill ..."}
            uses the inline content directly and reads nothing from disk.
        {"path": "skills/foo/SKILL.md", "name": "foo-bar"}
            reads the file and keys its result as ``"foo-bar"``.

    Returns:
        List of dicts with at least a ``"path"`` key.
    """
    entries: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    for line_no, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue  # skip blanks and comment lines

        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON on line {line_no} in {path}: {exc}"
            ) from exc

        # Entry may have inline "content" (no file path needed) OR reference a file via "path"
        if "path" not in entry and "content" not in entry:
            raise ValueError(
                f'Line {line_no} needs either "path" or "content" key in {path}'
            )
        entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Content reading
# ---------------------------------------------------------------------------


def _read_content(path: Path) -> str:
    """Read a file and strip any YAML frontmatter."""
    text = path.read_text(encoding="utf-8-sig")
    return _strip_frontmatter(text)


# ---------------------------------------------------------------------------
# Core scoring loop
# ---------------------------------------------------------------------------


def _score_file(
    path: Path,
    content: str | None = None,
    *,
    include_readability: bool = True,
    coherence_scorer: "CoherenceScorer | None" = None,
    weights: "ScoreWeights | None" = None,
    semantic_scorer: "SemanticScorer | None" = None,
    extra_vague_words: "str | Iterable[str] | None" = None,
) -> AnalysisResult:
    """Score a single file's content using ``analyze()``.

    Args:
        path: File path (used for reporting only; the actual content comes from *content* or disk).
        content: Pre-read content string. If ``None``, reads from disk.
        include_readability: Whether to compute readability metrics (default True).
        coherence_scorer: Optional embedding-based coherence scorer.
        weights: Custom score weights, passed to ``analyze()``.
        semantic_scorer: Custom semantic scorer, passed to ``analyze()``.
        extra_vague_words: Additional vague words, passed to ``analyze()``.

    Returns:
        An ``AnalysisResult`` for the file's content.
    """
    text = content if content is not None else _read_content(path)

    return analyze(
        text,
        include_readability=include_readability,
        coherence_scorer=coherence_scorer,
        weights=weights,
        semantic_scorer=semantic_scorer,
        extra_vague_words=extra_vague_words,
    )


# ---------------------------------------------------------------------------
# Public API: clarify()
# ---------------------------------------------------------------------------


def clarify(
    path: str | Path,
    *,
    include_readability: bool = True,
    coherence_scorer: "CoherenceScorer | None" = None,
    weights: "ScoreWeights | None" = None,
    semantic_scorer: "SemanticScorer | None" = None,
    extra_vague_words: "str | Iterable[str] | None" = None,
    pattern: str = "**/*.md",
    fmt: str = "auto",
    on_error: Literal["skip", "raise"] = "skip",
) -> AnalysisResult | dict[str, AnalysisResult] | list[tuple[Path, AnalysisResult]]:
    """Score a single file, batch JSONL, or directory recursively.

    This is the main entry point for clarity scoring of skill documents.
    It automatically detects the input type and returns the appropriate
    structure.

    Args:
        path: One of:
            * Single ``.md`` file path (e.g. ``"skills/foo/SKILL.md"``)
            * Directory to scan recursively (e.g. ``"skills/"``)
            * JSONL batch file with ``{"path": "..."}`` entries
        include_readability: Include readability metrics in results (default True).
        coherence_scorer: Optional embedding-based coherence scorer. If provided,
            each result will include ``context_coherence``. With the default
            ScoreWeights the readability and coherence weights are 0, so
            neither signal changes ``clarity_score`` unless *weights* gives
            them a weight above 0.
        weights: Custom score weights for every scored file, passed to
            ``analyze()``. ``None`` uses the default ScoreWeights.
        semantic_scorer: Custom semantic scorer for every scored file, passed
            to ``analyze()``. ``None`` uses WordnetPolysemyScorer.
        extra_vague_words: Additional vague words for every scored file,
            passed to ``analyze()``. A single string counts as one entry.
        pattern: Glob pattern for directory scanning (default ``**/*.md``).
            Set to ``"*/SKILL.md"`` to only find SKILL.md files.
        fmt: Output format hint — currently unused (auto-detection always applies).
        on_error: What directory and batch modes do with a file or entry that
            fails to read or score. ``"skip"`` (the default) leaves it out of
            the results and logs a warning on the ``prolix.clarify``
            logger. ``"raise"`` re-raises the error. A single file always
            raises.

    Returns:
        - Single file: ``AnalysisResult``
        - Directory scan: ``list[tuple[Path, AnalysisResult]]`` sorted by path
        - Batch JSONL: ``dict[str, AnalysisResult]`` keyed on ``"name"``, else the
          directory name of a ``SKILL.md`` path, else the ``"path"`` stem. A
          relative path is read from the batch file's directory when the file
          exists there, and from the working directory otherwise.

    Raises:
        FileNotFoundError: When the single-file path does not exist.
        NotADirectoryError: When the directory path is not a directory.
        ValueError: When JSONL lines are malformed or missing ``"path"`` key,
            or when *on_error* is not ``"skip"`` or ``"raise"``.
        UnicodeDecodeError: When a single file is not valid UTF-8.
        OSError: When a single file cannot be read.

    Examples::

        # Single file
        result = clarify("skills/brand/SKILL.md")
        print(result.clarity_score)  # → 42.3

        # Directory scan — find all SKILL.md files recursively
        results = clarify("skills/", pattern="*/SKILL.md")
        for path, res in results:
            print(f"{path.name}: {res.clarity_score:.1f}")

        # Batch JSONL
        results = clarify("batch.jsonl")
    """
    _check_on_error(on_error)
    path = Path(path)

    if fmt != "auto":
        import warnings
        warnings.warn(
            "The 'fmt' parameter is not yet fully supported; auto-detection always applies.",
            UserWarning,
            stacklevel=2,
        )

    options: dict[str, Any] = {
        "weights": weights,
        "semantic_scorer": semantic_scorer,
        "extra_vague_words": extra_vague_words,
    }

    # Detect input type and dispatch
    if path.is_file():
        # Check if it looks like a JSONL file
        if path.suffix == ".jsonl" or path.suffix == ".json":
            return _score_batch(
                path, include_readability, coherence_scorer, on_error=on_error, **options,
            )
        else:
            return _score_file(
                path, content=None,
                include_readability=include_readability,
                coherence_scorer=coherence_scorer,
                **options,
            )

    elif path.is_dir():
        return _score_directory(
            path, pattern, include_readability, coherence_scorer,
            on_error=on_error, **options,
        )

    else:
        raise FileNotFoundError(f"Path does not exist: {path}")


# ---------------------------------------------------------------------------
# Mode implementations
# ---------------------------------------------------------------------------


def _score_directory(
    dir_path: Path,
    pattern: str,
    include_readability: bool,
    coherence_scorer: "CoherenceScorer | None",
    *,
    on_error: Literal["skip", "raise"] = "skip",
    weights: "ScoreWeights | None" = None,
    semantic_scorer: "SemanticScorer | None" = None,
    extra_vague_words: "str | Iterable[str] | None" = None,
) -> list[tuple[Path, AnalysisResult]]:
    """Score all files matching *pattern* in *dir_path*.

    Returns a sorted list of ``(Path, AnalysisResult)`` tuples.
    With ``on_error="skip"`` a file that fails to read or score is left out
    and logged as a warning. With ``on_error="raise"`` the error propagates.
    """
    _check_on_error(on_error)
    discovered = _discover_directory(dir_path, pattern)

    results: list[tuple[Path, AnalysisResult]] = []
    for file_path in discovered:
        try:
            text = _read_content(file_path)
            result = analyze(
                text,
                include_readability=include_readability,
                coherence_scorer=coherence_scorer,
                weights=weights,
                semantic_scorer=semantic_scorer,
                extra_vague_words=extra_vague_words,
            )
            results.append((file_path, result))
        except Exception as exc:
            if on_error == "raise":
                raise
            logger.warning("failed to score %s: %s", file_path, exc)

    # Sort by resolved path for deterministic ordering
    results.sort(key=lambda x: x[0])
    return results


def _score_batch(
    batch_path: Path,
    include_readability: bool,
    coherence_scorer: "CoherenceScorer | None",
    *,
    on_error: Literal["skip", "raise"] = "skip",
    weights: "ScoreWeights | None" = None,
    semantic_scorer: "SemanticScorer | None" = None,
    extra_vague_words: "str | Iterable[str] | None" = None,
) -> dict[str, AnalysisResult]:
    """Score entries from a JSONL batch file.

    Each line is a JSON object with a ``"path"`` key, a ``"content"`` key, or
    both. If the line has a ``"content"`` key, that string is used directly
    instead of reading from disk. A relative ``"path"`` is read from the
    batch file's directory when the file exists there, and from the working
    directory otherwise. With ``on_error="skip"`` an entry that fails to read
    or score is left out and logged as a warning. With ``on_error="raise"``
    the error propagates.

    Returns:
        Dict mapping a key to the ``AnalysisResult``. The key is ``"name"`` if
        present, else the parent directory name when the file is named
        ``SKILL.md``, else the stem of ``"path"``, else ``entry_N``. When that
        key is already taken the raw ``"path"`` is used instead, and a number
        is appended if that is taken too, so no result is overwritten.
    """
    _check_on_error(on_error)
    entries = _discover_batch_jsonl(batch_path)

    results: dict[str, AnalysisResult] = {}
    for entry in entries:
        raw_path = entry.get("path", "")
        entry_path = Path(raw_path)
        # Prefer a file next to the batch file; keep CWD-relative paths working.
        if raw_path and not entry_path.is_absolute():
            batch_relative = batch_path.parent / entry_path
            if batch_relative.is_file():
                entry_path = batch_relative
        content_inline = entry.get("content")

        # Key is "name", else the skill directory of a SKILL.md, else the file
        # stem or entry index. A taken key falls back to the raw path.
        key = entry.get("name")
        if not key and entry_path.name == "SKILL.md":
            key = Path(os.path.abspath(entry_path)).parent.name
        if not key:
            key = entry_path.stem if entry_path.name else f"entry_{len(results)}"
        if key in results:
            key = raw_path or key
        base_key, suffix = key, 2
        while key in results:
            key = f"{base_key} ({suffix})"
            suffix += 1

        try:
            if content_inline:
                # Inline content — no file reading needed
                result = analyze(
                    _strip_frontmatter(content_inline),
                    include_readability=include_readability,
                    coherence_scorer=coherence_scorer,
                    weights=weights,
                    semantic_scorer=semantic_scorer,
                    extra_vague_words=extra_vague_words,
                )
            elif entry_path.is_file():
                result = _score_file(
                    entry_path,
                    include_readability=include_readability,
                    coherence_scorer=coherence_scorer,
                    weights=weights,
                    semantic_scorer=semantic_scorer,
                    extra_vague_words=extra_vague_words,
                )
            else:
                # content is required if file path doesn't exist
                raise ValueError(f'Batch entry has no "content" and file not found: {entry_path}')

            results[key] = result
        except Exception as exc:
            if on_error == "raise":
                raise
            logger.warning("failed to score %s: %s", entry_path, exc)

    return results


# ---------------------------------------------------------------------------
# Convenience: one-line model comparison helper
# ---------------------------------------------------------------------------


def compare_models(
    model_names: list[str],
    path: str | Path,
    *,
    pattern: str = "**/*.md",
    include_readability: bool = True,
) -> dict[str, list[tuple[Path, AnalysisResult]]]:
    """Score all files with multiple coherence models for benchmarking.

    Convenience function that runs ``clarify()`` once per model and returns
    results grouped by model name.  The first entry in the list is scored
    without any coherence scorer and its results are keyed ``"<baseline>"``,
    then subsequent models each load their embedding model.

    Deprecated: this experimental research tool emits a ``DeprecationWarning``
    and will be removed in prolix 0.4.0.

    Args:
        model_names: HuggingFace model names to compare
            (e.g. ``["all-MiniLM-L6-v2", "all-mpnet-base-v2"]``).
        path: File, directory, or JSONL batch to score.
        pattern: Glob pattern for directory scanning.
        include_readability: Include readability metrics (default True).

    Returns:
        Dict mapping ``"<baseline>"`` and each later model name to a list of
        ``(Path, AnalysisResult)`` tuples.

    Raises:
        ImportError: If any embedding model fails to load and is not the first (baseline).
    """
    from pathlib import Path as _Path

    from .model_compare import _warn_deprecated

    _warn_deprecated("compare_models()")

    all_results: dict[str, list[tuple[Path, AnalysisResult]]] = {}

    for idx, model_name in enumerate(model_names):
        # Load coherence scorer (skip for baseline / first model)
        coherence_scorer = None
        if idx > 0:
            from .semantic_coherence import MiniLMCoherenceScorer
            coherence_scorer = MiniLMCoherenceScorer(model_name)

        input_path = _Path(path)
        mode_results: list[tuple[Path, AnalysisResult]] = []

        if input_path.is_file() and input_path.suffix == ".jsonl":
            # Batch JSONL — return as dict values converted to list
            batch = _score_batch(input_path, include_readability, coherence_scorer)
            mode_results = [(Path(k), v) for k, v in sorted(batch.items())]
        elif input_path.is_dir():
            mode_results = _score_directory(
                input_path, pattern, include_readability, coherence_scorer,
            )
        else:
            # Single file — wrap in list
            result = analyze(
                _read_content(input_path),
                include_readability=include_readability,
                coherence_scorer=coherence_scorer,
            )
            mode_results = [(input_path, result)]

        all_results["<baseline>" if idx == 0 else model_name] = mode_results

    return all_results
