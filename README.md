# clarity_score (Python)

WordNet + syntactic-ambiguity + vagueness sentence scoring. See the
[repo root README](../README.md) and [ARCHITECTURE.md](../ARCHITECTURE.md)
for the full design.

## Setup

```bash
pip install -e ".[dev]"
python -c "import wn; wn.download('oewn:2025')"  # one-time, ~11MB
pytest
```

## Usage

```python
from clarity_score import analyze

result = analyze("Make a peanut butter sandwich")
print(result.clarity_score, result.to_json())
```

```bash
clarity-score "The chef stirred the soup with the spoon" --json
```
