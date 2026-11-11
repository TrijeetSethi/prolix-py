"""Command-line interface for prolix.

Usage:
    # Score a single sentence, file or standard input
    prolix "The cat sat on the mat."
    prolix my-skill.md --json
    prolix - < my-skill.md

    # Score every matching file in a directory
    prolix dir skills/
    prolix dir /path/to/skills/ --output results.csv

    # Print the version
    prolix --version

python -m prolix runs the same command. prolix-dir is an alias
of prolix dir. To score the word dir itself, run prolix -- dir.
"""

from __future__ import annotations

import argparse
import csv
import functools
import io
import json
import math
import os
import statistics as _stats
import sys
import time
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import ParamSpec, TextIO

from . import __version__

__all__ = ["main", "entry_single", "entry_dir", "entry_compare"]

# Exit code for missing NLTK or WordNet data, distinct from exit code 1,
# which reports a failed run or a score below --fail-under.
_EXIT_MISSING_DATA = 2

# Exit code for missing or unreadable input to prolix.
_EXIT_BAD_INPUT = 2

# A single word with one of these suffixes is taken to be a file path.
_TEXT_FILE_SUFFIXES = (".md", ".markdown", ".txt")

_READABILITY_HELP = "Also report a readability score."
_COHERENCE_HELP = (
    "Report embedding coherence, which needs the semantic-coherence extra. "
    "It changes the score only when a coherence weight is set."
)

_SINGLE_EPILOG = """\
examples:
  prolix "Click the Save button to store the file."
  prolix SKILL.md --json --fail-under 40
  prolix - < SKILL.md
  prolix dir skills/ --output results.csv
  prolix --json -- dir

INPUT is a file, - for standard input, or the text to score. YAML front matter
is removed from a file or standard input before it is scored. A first argument
of dir scores every matching file in a directory, so pass the word dir after --
to score it as text.

The output has one line for each of the clarity, lexical, specificity, syntax
and readability scores and one for the number of words scored. --json prints
the same fields as a JSON object. Every score runs from 0 to 100 and a higher
value means clearer text. Input with no words to score is reported as skipped,
prints no scores without --json and passes --fail-under.

The exit status is 0 on success, 1 when the clarity score is below --fail-under,
and 2 for a usage error, unreadable input or missing language data.
"""


_P = ParamSpec("_P")


def _finite_float(value: str) -> float:
    """Parse a --fail-under value, rejecting NaN and infinity with a usage error."""
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid number: {value!r}") from None
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError(f"must be a finite number, not {value!r}")
    return number


def _flush_stdout() -> None:
    """Flush stdout, which Python sets to None when file descriptor 1 is closed."""
    if sys.stdout is not None:
        sys.stdout.flush()


def _silence_broken_stream(stream: TextIO | None) -> None:
    """Point a stream at os.devnull when its reader has gone.

    A stream that cannot be flushed would fail again when the interpreter
    flushes it at exit, which then exits with 120. A stream that flushes is
    left alone.
    """
    if stream is None:
        return
    try:
        stream.flush()
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, stream.fileno())
        os.close(devnull)


def _report(message: str) -> None:
    """Print one status line on stderr. A closed stderr cannot change the exit status."""
    try:
        print(message, file=sys.stderr)
    except BrokenPipeError:
        pass


def _exit_quietly_on_broken_pipe(entry: Callable[_P, int]) -> Callable[_P, int]:
    """Make a command end without a message when its output reader closes early.

    The flush runs inside the try, so a closed pipe is caught here and not
    reported by the interpreter at exit. Stdout and stderr, which share the
    pipe with 2>&1, then point at os.devnull if they cannot be flushed, so
    the flush at exit cannot fail again. A command that returned before the
    pipe error keeps its exit status, so a score below --fail-under still
    exits with 1. A command stopped while it was still writing returns 0.
    The --help and --version options print and then raise SystemExit, so
    their output is flushed inside the try as well. A closed stdout, which
    Python sets to None, is not flushed.
    """

    @functools.wraps(entry)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> int:
        code = 0
        try:
            try:
                code = entry(*args, **kwargs)
            except SystemExit:
                _flush_stdout()
                raise
            _flush_stdout()
        except BrokenPipeError:
            pass
        finally:
            for stream in (sys.stdout, sys.stderr):
                _silence_broken_stream(stream)
        return code

    return wrapper


@_exit_quietly_on_broken_pipe
def main(argv: list[str] | None = None) -> int:
    """Run the ``prolix`` command and dispatch to its subcommands.

    A first argument of ``dir`` runs ``entry_dir()`` and ``compare`` runs
    ``entry_compare()``. Any other arguments score one sentence or file with
    ``entry_single()``. Arguments after ``--`` are never taken as a subcommand.
    The ``compare`` subcommand calls ``entry_compare()``, which is deprecated and
    emits a ``DeprecationWarning``. It will be removed in prolix 0.4.0.
    """
    if argv is None:
        argv = sys.argv[1:]

    # Detect explicit subcommand in argv
    if argv and argv[0] == "dir":
        return entry_dir(argv[1:])
    elif argv and argv[0] == "compare":
        return entry_compare(argv[1:])

    # Fallback: single-file/sentence analysis (backward compatible)
    return entry_single(argv)


# ---------------------------------------------------------------------------
# Entry points (used as scripts — each has its own parser, no conflict)
# ---------------------------------------------------------------------------


@_exit_quietly_on_broken_pipe
def entry_single(argv: list[str] | None = None) -> int:
    """Score one sentence, file or standard input with ``Clarity``, the default command."""
    parser = argparse.ArgumentParser(
        prog="prolix",
        description="Score the clarity of a sentence or a Markdown file.",
        epilog=_SINGLE_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "input", metavar="INPUT", help="a file to score, - for standard input, or the text itself",
    )
    parser.add_argument("--json", action="store_true", help="print the scores as a JSON object")
    parser.add_argument(
        "--fail-under", type=_finite_float, default=0.0, metavar="SCORE",
        help="exit with code 1 if the clarity score is below SCORE",
    )

    args = parser.parse_args(argv)
    return _run(_cmd_single, args)


@_exit_quietly_on_broken_pipe
def entry_dir(argv: list[str] | None = None) -> int:
    """Entry point for ``prolix dir`` and its ``prolix-dir`` alias."""
    # Directory and file names are printed with backslash escapes when stdout
    # cannot encode them, as with redirected output on Windows.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(
        prog="prolix dir",
        description="Score all files in a directory.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("target", help="Directory containing skill files")
    parser.add_argument("--pattern", "-p", default="**/SKILL.md", help="Glob pattern (default: **/SKILL.md)")
    parser.add_argument("--output", "-o", help="Output file (CSV or JSON)")
    parser.add_argument("--readability", "-r", action="store_true", help=_READABILITY_HELP)
    parser.add_argument("--coherence", action="store_true", help=_COHERENCE_HELP)

    args = parser.parse_args(argv)
    return _run(_cmd_dir, args)


def entry_compare(argv: list[str] | None = None) -> int:
    """Run the deprecated model comparison command.

    Model comparison is an experimental research tool. This function emits a
    ``DeprecationWarning`` and will be removed in prolix 0.4.0. It also
    prints a warning line on stderr, because Python hides that warning from
    the prolix command by default.
    """
    from .model_compare import _warn_deprecated

    _warn_deprecated("The compare subcommand of prolix.cli")
    print("warning: the compare subcommand is deprecated and will be removed in "
          "prolix 0.4.0", file=sys.stderr)
    parser = argparse.ArgumentParser(
        prog="python -m prolix.cli compare",
        description=(
            "Compare coherence models on a set of documents. Deprecated: this "
            "experimental research tool will be removed in prolix 0.4.0."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--target", "-t", required=True, help="Directory containing skill files")
    parser.add_argument(
        "--model", dest="model", action="append", default=None,
        help=("HuggingFace model name, repeat to compare several "
              "(default: all-MiniLM-L6-v2 and all-mpnet-base-v2)"),
    )
    parser.add_argument("--pattern", "-p", default="**/SKILL.md", help="Glob pattern (default: **/SKILL.md)")
    parser.add_argument("--output", "-o", required=True, help="Output JSON file path")
    parser.add_argument("--readability", "-r", action="store_true", help="Include readability metrics")

    args = parser.parse_args(argv)
    return _run(_cmd_compare, args)


def _is_missing_data(exc: BaseException) -> bool:
    """True for the LookupError raised when NLTK or WordNet data is missing.

    KeyError and IndexError are LookupError subclasses too, but they mean a
    bug, so they are not treated as missing data.
    """
    return isinstance(exc, LookupError) and not isinstance(exc, (KeyError, IndexError))


def _run(handler: Callable[[argparse.Namespace], int], args: argparse.Namespace) -> int:
    """Run a subcommand handler and report missing language data in one line."""
    try:
        return handler(args)
    except LookupError as exc:
        if not _is_missing_data(exc):
            raise
        print(f"Error: {exc}", file=sys.stderr)
        return _EXIT_MISSING_DATA


# ---------------------------------------------------------------------------
# Subcommand handlers (shared logic between entry points and main dispatcher)
# ---------------------------------------------------------------------------


def _cmd_single(args: argparse.Namespace) -> int:
    """Score one sentence, file or standard input with Clarity and print the scores."""
    from .clarify import _read_content, _strip_frontmatter
    from .clarity import Clarity

    text = args.input
    if args.input == "-":
        # Read standard input like a file: UTF-8, front matter stripped.
        if sys.stdin is None:
            # Python sets sys.stdin to None when file descriptor 0 is closed.
            print("error: cannot read standard input: it is closed", file=sys.stderr)
            return _EXIT_BAD_INPUT
        try:
            text = _strip_frontmatter(sys.stdin.buffer.read().decode("utf-8-sig"))
        except (OSError, UnicodeDecodeError) as exc:
            print(f"error: cannot read standard input: {exc}", file=sys.stderr)
            return _EXIT_BAD_INPUT
    elif args.input:
        # Check if it's a file path that exists, or treat as a sentence. An
        # empty argument is text with no words, because Path("") is the
        # current directory.
        path = Path(args.input)
        try:
            is_file = path.is_file()
            is_dir = not is_file and path.is_dir()
        except (OSError, ValueError):
            # Before Python 3.14, is_file() raises OSError (ENAMETOOLONG) when the
            # text is longer than the file name limit, so treat it as text.
            is_file = is_dir = False
        if is_dir:
            print(f"error: {args.input} is a directory, use prolix dir", file=sys.stderr)
            return _EXIT_BAD_INPUT
        if is_file:
            # Read like clarify() and prolix dir: UTF-8, front matter stripped.
            try:
                text = _read_content(path)
            except (OSError, UnicodeDecodeError) as exc:
                print(f"error: cannot read {args.input}: {exc}", file=sys.stderr)
                return _EXIT_BAD_INPUT
        elif (path.suffix.lower() in _TEXT_FILE_SUFFIXES
              and not any(ch.isspace() for ch in args.input)):
            print(f"error: cannot read {args.input}: no such file", file=sys.stderr)
            return _EXIT_BAD_INPUT

    scores = Clarity().score(text)

    if args.json:
        print(json.dumps(scores.to_dict(), indent=2))
    elif scores.words > 0:
        # Text with no words prints no score lines, as the Rust command does.
        for name, value in scores.to_dict().items():
            print(f"{name} {value:.2f}" if isinstance(value, float) else f"{name} {value}")

    if scores.words == 0:
        _report("skipped: no words to score")
        return 0
    if scores.clarity < args.fail_under:
        _report(f"fail: clarity {scores.clarity:.2f} is below {args.fail_under:g}")
        return 1
    return 0


def _cmd_dir(args: argparse.Namespace) -> int:
    """Handle the ``prolix dir`` subcommand."""
    from .clarify import _discover_directory, _score_file

    skills_path = Path(args.target)
    if not skills_path.is_dir():
        print(f"Error: not a directory: {skills_path}", file=sys.stderr)
        return 1

    files = sorted(_discover_directory(skills_path, args.pattern))

    if not files:
        print(f"No files found matching '{args.pattern}' in {skills_path}", file=sys.stderr)
        return 1

    print(f"Found {len(files)} file(s) in {args.target}\n")

    # Load coherence scorer if requested
    coherence_scorer = None
    if hasattr(args, "coherence") and args.coherence:
        try:
            from .semantic_coherence import MiniLMCoherenceScorer
            coherence_scorer = MiniLMCoherenceScorer()
        except ImportError as exc:
            print(f"Warning: coherence feature not available ({exc})", file=sys.stderr)

    results: list[tuple[str, dict]] = []
    errors: list[tuple[str, str]] = []

    for skill_file in files:
        try:
            result = _score_file(
                skill_file,
                include_readability=args.readability,
                coherence_scorer=coherence_scorer,
            )
            row: dict = {
                "name": skill_file.parent.name,
                "path": str(skill_file),
                "clarity_score": round(result.clarity_score, 2),
                "semantic_ambiguity": round(result.semantic_ambiguity, 2),
                "specificity": round(result.specificity, 2),
                "avg_word_senses": round(result.lexical.avg_senses, 2),
                "avg_wordnet_depth": round(result.lexical.avg_depth, 2),
                "syntax_ambiguity_hits": len(result.syntax.hits),
                "vague_word_hits": len(result.vague_hits),
            }
            # Add structural clarity
            if result.structural_clarity is not None:
                row["structural_clarity"] = round(result.structural_clarity, 2)
            # Add readability
            if result.readability_score is not None:
                row["readability_score"] = round(result.readability_score, 2)
            # Add coherence
            if result.context_coherence is not None:
                row["context_coherence"] = round(result.context_coherence, 2)
        except Exception as exc:
            if _is_missing_data(exc):
                raise
            errors.append((str(skill_file), str(exc)))
            print(f"  error {skill_file.parent.name:30s} {exc}", file=sys.stderr)
            continue

        results.append((str(skill_file), row))
        print(f"  ok    {skill_file.parent.name:30s} clarity={row['clarity_score']:5.1f}")

    # Export to CSV or JSON
    if args.output and results:
        output_path = Path(args.output)
        suffix = output_path.suffix.lower()
        # structural_clarity is left out of rows for single-line files, so the
        # header lists the keys of every row and a missing cell stays empty.
        keys = list(dict.fromkeys(key for _, row in results for key in row))

        if suffix == ".json":
            # Export just the dicts (strip path keys for cleaner JSON)
            export_data = [dict(row) for _, row in results]
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2)
            print(f"\nExported {len(results)} results to {output_path}")
        else:  # CSV (default)
            with output_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                for _, row in results:
                    writer.writerow(row)
            print(f"\nExported {len(results)} results to {output_path}")

    if errors:
        print(f"\n{len(errors)} file(s) failed", file=sys.stderr)

    # Print summary stats (unless --output is a JSON file or explicit json flag)
    export_json = args.output and Path(args.output).suffix == ".json" if args.output else False
    if not export_json and results:
        scores = [r["clarity_score"] for _, r in results]
        c_mean = _stats.mean(scores)
        c_std = _stats.stdev(scores) if len(scores) > 1 else 0
        print(f"\n{'-' * 45}")
        print(f"Clarity: mean={c_mean:.1f}, std={c_std:.1f}, n={len(results)}")

    return 1 if errors else 0


def _cmd_compare(args: argparse.Namespace) -> int:
    """Handle the deprecated ``compare`` subcommand."""
    from .model_compare import compare_models_benchmark, BenchmarkResult, generate_recommendation

    target_path = Path(args.target)
    if not target_path.is_dir():
        print(f"Error: not a directory: {target_path}", file=sys.stderr)
        return 1

    model_names = args.model or ["all-MiniLM-L6-v2", "all-mpnet-base-v2"]
    pattern = args.pattern or "**/SKILL.md"

    print(f"Comparing {len(model_names)} model(s) on {args.target}\n")
    for idx, name in enumerate(model_names):
        print(f"  Model {idx+1}: {name}")
    print()

    t0 = time.time()
    with warnings.catch_warnings():
        # entry_compare() has already warned that model comparison is deprecated.
        warnings.filterwarnings(
            "ignore", r"compare_models_benchmark\(\) is deprecated", DeprecationWarning,
        )
        result: BenchmarkResult = compare_models_benchmark(
            model_names=model_names,
            path=target_path,
            pattern=pattern,
            include_readability=args.readability,
            output_csv=None,
            output_json=None,  # We handle JSON output ourselves
        )
    total = time.time() - t0

    print(f"\nTotal benchmark time: {total:.1f}s")

    if not result.comparisons:
        print("Error: no comparison ran, because fewer than two models were scored",
              file=sys.stderr)
        return 1

    # Print recommendations
    print("\n" + "=" * 60)
    rec = generate_recommendation(result.comparisons)
    print(f"RECOMMENDATION: {rec}")

    # Export to JSON
    output_path = Path(args.output)
    with output_path.open("w", encoding="utf-8") as f:
        f.write(result.to_json())
    print(f"\nJSON results saved to: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
