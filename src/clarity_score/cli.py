from __future__ import annotations

import argparse
import json
import sys

from .scoring import analyze, ScoreWeights


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clarity-score",
        description=__doc__,
    )
    parser.add_argument("sentence", help="the sentence to analyze")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--readability", action="store_true", help="include readability metrics (Flesch-Kincaid, Gunning Fog, SMOG)")
    parser.add_argument(
        "--fail-under", type=float, default=0.0,
        help="exit with code 1 if clarity score is below this threshold",
    )
    args = parser.parse_args(argv)

    # Try to load coherence scorer if user requests it (graceful degradation)
    coherence_scorer = None
    if hasattr(args, "coherence") and args.coherence:
        try:
            from .semantic_coherence import MiniLMCoherenceScorer
            coherence_scorer = MiniLMCoherenceScorer()
        except ImportError as exc:
            print(f"Warning: coherence feature not available ({exc})", file=sys.stderr)

    result = analyze(
        args.sentence,
        include_readability=args.readability,
        coherence_scorer=coherence_scorer,
    )

    if args.json:
        print(json.dumps(result.to_json(), indent=2))
        return 0

    print(f"Sentence: {result.sentence!r}")
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
    if result.readability_score is not None:
        print(f"  Readability score:      {result.readability_score:.1f}/100")
    if result.context_coherence is not None:
        print(f"  Context coherence:      {result.context_coherence:.1f}/100")

    if args.fail_under > 0.0 and result.clarity_score < args.fail_under:
        print(f"\nFail: clarity score {result.clarity_score:.1f} < threshold {args.fail_under}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
