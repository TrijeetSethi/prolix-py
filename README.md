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
clarity-score-dir skills/ --output results.csv
clarity-score-dir /path/to/skills/ -p "**/*.md" --readability

# Compare coherence models
clarity-score-compare \
    --model all-MiniLM-L6-v2 --model all-mpnet-base-v2 \
    --target skills/ \
    --output comparison.json
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
