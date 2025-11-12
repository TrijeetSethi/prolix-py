from __future__ import annotations

import argparse
import json
import sys

from .scoring import analyze


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clarity-score", description=__doc__)
    parser.add_argument("sentence", help="the sentence to analyze")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)

    result = analyze(args.sentence)

    if args.json:
        print(json.dumps(result.to_json(), indent=2))
        return 0

    print(f"Sentence: {result.sentence!r}")
    print(f"  Clarity score:        {result.clarity_score:.1f}/100")
    print(f"  Semantic ambiguity:   {result.semantic_ambiguity:.1f}")
    print(f"  Specificity:          {result.specificity:.1f}")
    print(f"  Avg word senses:      {result.lexical.avg_senses:.2f}")
    print(f"  Avg WordNet depth:    {result.lexical.avg_depth:.2f}")
    print(f"  Syntax ambiguity hits: {len(result.syntax.hits)}")
    for hit in result.syntax.hits:
        print(f"    - {hit.kind}: {hit.span!r}")
    if result.vague_hits:
        print(f"  Vague-word hits: {len(result.vague_hits)}")
        for hit in result.vague_hits:
            print(f"    - {hit.phrase!r} (-{hit.penalty:g})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
