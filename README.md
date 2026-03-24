# clarity_score — Clarity Scoring for Natural Language

WordNet-backed + syntactic-ambiguity + vagueness sentence/document scoring.

See the [repo root README](../README.md) and [ARCHITECTURE.md](../ARCHITECTURE.md) for the full design.

## Quick Start

```python
from clarity_score import analyze, AnalysisResult

result = analyze("The chef stirred the soup with the spoon.")
print(result.clarity_score)        # → ~47/100
print(result.to_json())            # → dict with all sub-scores
```

### Optional Signals (install extras)

```bash
# Readability formulas (zero deps — Flesch-Kincaid, Gunning Fog, SMOG)
pip install clarity-score[readability]

# Embedding-based coherence scoring (requires sentence-transformers ~24MB model download)
pip install clarity-score[semantic-coherence]
```

```python
from clarity_score import analyze
from clarity_score.scorer import WordnetPolysemyScorer

# Full analysis with readability enabled
result = analyze("The chef stirred the soup.", include_readability=True)
print(result.readability_score)      # → ~65/100

# With coherence scoring
from clarity_score.semantic_coherence import MiniLMCoherenceScorer
coherence_scorer = MiniLMCoherenceScorer()
result = analyze("The chef stirred the soup.", coherence_scorer=coherence_scorer)
print(result.context_coherence)      # → ~80-95 (high for coherent sentence)
```

## CLI Usage

```bash
# Single sentence or file
clarity-score "Make a peanut butter sandwich" --json
clarity-score my-skill.md

# Directory scan (default: **/SKILL.md)
clarity-score dir skills/ --output results.csv
clarity-score dir /path/to/skills/ -p "**/*.md" --readability
```

## API Reference

### Core Functions

| Function | Module | Purpose |
|----------|--------|---------|
| `analyze()` | `clarity_score` | Full clarity analysis of text |
| `clarify(path)` | `clarity_score.clarify` | Score files, directories, or batch JSONL |
| `extract_primitives(text)` | `clarity_score.primitives` | Compute all signals once, apply N formulas |
| `apply_formula(prim, weights)` | `clarity_score.primitives` | Apply formula preset to primitives |

### Data Classes

| Class | Description |
|-------|-------------|
| `AnalysisResult` | Full analysis result with all sub-scores |
| `ScoreWeights` | Configurable weights for the scoring formula |
| `ClarityPrimitives` | All raw signals (for multi-formula evaluation) |
| `LexicalReport` | WordNet sense depth and polysemy info |
| `SyntaxReport` | Detected structural ambiguity patterns |

## Installation

```bash
pip install clarity-score
# One-time: downloads Open English WordNet (~11MB) on first use
python -c "import wn; wn.download('oewn:2025')"

# Development
pip install clarity-score[dev]
pytest
```

### Known First-Use Downloads

| Dependency | What it downloads | Size | When |
|------------|-------------------|------|------|
| `wn` | Open English WordNet (oewn:2025) | ~11MB | On first `analyze()` call |
| `nltk` | punkt_tab, averaged_perceptron_tagger | ~30MB | Auto-downloaded on first import |
| `sentence-transformers` | all-MiniLM-L6-v2 model | ~24MB | On first `MiniLMCoherenceScorer()` (optional) |

## Testing

```bash
pip install -e ".[dev]"
pytest python/tests/ --tb=short -q
# 139 passed, 2 skipped (requires sentence-transformers)
```

## Data and attribution

The package bundles no WordNet or NLTK data. At run time it reads
Open English WordNet 2025 (https://en-word.net, Copyright 2019-present The
Open English WordNet Team, licensed under CC BY 4.0,
https://creativecommons.org/licenses/by/4.0/), which you download with
`wn.download('oewn:2025')`. Open English WordNet is derived from Princeton
WordNet 3.0 (Copyright 2006 by Princeton University). The package also
downloads the NLTK `punkt_tab` tokenizer and `averaged_perceptron_tagger_eng`
tagger models from NLTK Data, which are distributed under their own licenses.

## License

clarity-score is licensed under either the MIT license (`LICENSE-MIT`) or the
Apache License, Version 2.0 (`LICENSE-APACHE-2.0`), at your option. The
`rust/NOTICE` file in the source repository gives the full WordNet attribution
and reproduces the Princeton WordNet 3.0 license.

Unless you explicitly state otherwise, any contribution intentionally
submitted for inclusion in the work by you, as defined in the Apache-2.0
license, shall be dual licensed as above, without any additional terms or
conditions.
