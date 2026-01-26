"""Command-line interface for clarity_score.

Usage:
    # Analyze a single sentence or file
    clarity-score "The cat sat on the mat."
    clarity-score my-skill.md --json

    # Score all skills in a directory (new subcommand)
    clarity-score-dir skills/
    clarity-score-dir /path/to/skills/ --output results.csv

    # Compare MiniLM vs MPNet coherence models (new subcommand)
    clarity-score-compare \
        --model all-MiniLM-L6-v2 --model all-mpnet-base-v2 \
        --target skills/ \
        --output comparison.json
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics as _stats
import sys
import time
from collections.abc import Callable
from pathlib import Path

__all__ = ["main", "entry_single", "entry_dir", "entry_compare"]

# Exit code for missing NLTK or WordNet data, distinct from exit code 1,
# which reports a failed run or a score below --fail-under.
_EXIT_MISSING_DATA = 2


def main(argv: list[str] | None = None) -> int:
    """Top-level entry point — dispatches to subcommand handlers.

    Supports both the legacy `clarity-score "sentence"` usage and the new
    subcommands via the ``dir`` and ``compare`` keywords as the first argument.
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


def entry_single(argv: list[str] | None = None) -> int:
    """Entry point for `clarity-score` — single sentence/file analysis."""
    parser = argparse.ArgumentParser(
        prog="clarity-score",
        description=__doc__.strip(),
    )
    parser.add_argument("sentence", help="the sentence or file to analyze")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--readability", "-r", action="store_true", help="include readability metrics (Flesch-Kincaid, Gunning Fog, SMOG)")
    parser.add_argument(
        "--fail-under", type=float, default=0.0,
        help="exit with code 1 if clarity score is below this threshold",
    )
    parser.add_argument(
        "--coherence", action="store_true",
        help="enable coherence scoring (requires sentence-transformers)",
    )

    args = parser.parse_args(argv)
    return _run(_cmd_single, args)


def entry_dir(argv: list[str] | None = None) -> int:
    """Entry point for `clarity-score-dir` — directory scanning."""
    parser = argparse.ArgumentParser(
        prog="clarity-score-dir",
        description="Score all files in a directory.",
    )
    parser.add_argument("target", help="Directory containing skill files")
    parser.add_argument("--pattern", "-p", default="**/SKILL.md", help="Glob pattern (default: **/SKILL.md)")
    parser.add_argument("--output", "-o", help="Output file (CSV or JSON)")
    parser.add_argument("--readability", "-r", action="store_true", help="Include readability metrics")
    parser.add_argument(
        "--coherence", action="store_true",
        help="Enable coherence scoring (requires sentence-transformers)",
    )

    args = parser.parse_args(argv)
    return _run(_cmd_dir, args)


def entry_compare(argv: list[str] | None = None) -> int:
    """Entry point for `clarity-score-compare` — model comparison."""
    parser = argparse.ArgumentParser(
        prog="clarity-score-compare",
        description="Compare coherence models on a set of documents.",
    )
    parser.add_argument("--target", "-t", required=True, help="Directory containing skill files")
    parser.add_argument(
        "--model", dest="model", action="append", default=["all-MiniLM-L6-v2", "all-mpnet-base-v2"],
        help="HuggingFace model name (can specify multiple)",
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
    """Handle single-file / sentence analysis."""
    from .scoring import analyze

    if not args.sentence:
        print("Error: no sentence or file specified. Usage:\n"
              "  clarity-score \"The cat sat on the mat.\" --json\n"
              "  clarity-score my-skill.md --json", file=sys.stderr)
        return 1

    # Check if it's a file path that exists, or treat as a sentence
    text = args.sentence
    sent_path = Path(args.sentence)
    if sent_path.is_file():
        text = sent_path.read_text(encoding="utf-8-sig")

    # Try to load coherence scorer if requested (graceful degradation)
    coherence_scorer = None
    if hasattr(args, "coherence") and args.coherence:
        try:
            from .semantic_coherence import MiniLMCoherenceScorer
            coherence_scorer = MiniLMCoherenceScorer()
        except ImportError as exc:
            print(f"Warning: coherence feature not available ({exc})", file=sys.stderr)

    result = analyze(
        text,
        include_readability=args.readability,
        coherence_scorer=coherence_scorer,
    )
    failed = args.fail_under > 0.0 and result.clarity_score < args.fail_under

    if args.json:
        print(json.dumps(result.to_json(), indent=2))
        return 1 if failed else 0

    display_label = sent_path.name if sent_path.is_file() else args.sentence
    print(f"Sentence: {display_label!r}")
    print(f"  Clarity score:          {result.clarity_score:.1f}/100")
    print(f"  Semantic ambiguity:     {result.semantic_ambiguity:.1f}")
    print(f"  Specificity:            {result.specificity:.1f}")
    print(f"  Avg word senses:        {result.lexical.avg_senses:.2f}")
    print(f"  Avg WordNet depth:      {result.lexical.avg_depth:.2f}")
    print(f"  Syntax ambiguity hits:  {len(result.syntax.hits)}")
    for hit in result.syntax.hits:
        print(f"    - {hit.kind}: {hit.span!r}")
    if result.vague_hits:
        print(f"  Vague-word hits:        {len(result.vague_hits)}")
        for hit in result.vague_hits:
            print(f"    - {hit.phrase!r} (-{hit.penalty:g})")
    if hasattr(result, "structural_clarity"):
        print(f"  Structural clarity:     {result.structural_clarity:.1f}/100")
    if result.readability_score is not None:
        print(f"  Readability score:      {result.readability_score:.1f}/100")
    if result.context_coherence is not None:
        print(f"  Context coherence:      {result.context_coherence:.1f}/100")

    if failed:
        print(f"\nFail: clarity score {result.clarity_score:.1f} < threshold {args.fail_under}", file=sys.stderr)
        return 1

    return 0


def _cmd_dir(args: argparse.Namespace) -> int:
    """Handle the `clarity-score-dir` subcommand."""
    from .clarify import clarify, _discover_directory

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
            result = clarify(skill_file, include_readability=args.readability, coherence_scorer=coherence_scorer)
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
            if hasattr(result, "structural_clarity"):
                row["structural_clarity"] = round(result.structural_clarity, 2)
            # Add readability
            if result.readability_score is not None:
                row["readability_score"] = round(result.readability_score, 2)
            # Add coherence
            if result.context_coherence is not None:
                row["context_coherence"] = round(result.context_coherence, 2)

            results.append((str(skill_file), row))
            print(f"  ✓ {skill_file.parent.name:30s} → clarity={row['clarity_score']:5.1f}")
        except Exception as exc:
            if _is_missing_data(exc):
                raise
            errors.append((str(skill_file), str(exc)))
            print(f"  ✗ {skill_file.parent.name:30s} → ERROR: {exc}", file=sys.stderr)

    # Export to CSV or JSON
    if args.output and results:
        output_path = Path(args.output)
        suffix = output_path.suffix.lower()
        keys = list(results[0][1].keys())

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
        print(f"\n{'─' * 45}")
        print(f"Clarity: mean={c_mean:.1f}, std={c_std:.1f}, n={len(results)}")
        if c_std < 10:
            print("  ⚠ LOW VARIANCE (std < 10): consider adding structural signal")

    return 1 if errors else 0


def _cmd_compare(args: argparse.Namespace) -> int:
    """Handle the `clarity-score-compare` subcommand."""
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

    # Print recommendations
    if result.comparisons:
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
