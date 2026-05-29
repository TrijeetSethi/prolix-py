# clarity-score

Heuristic clarity and vagueness scoring for English prose.

clarity-score gives a sentence or a whole document a set of scores from 0 to
100, where a higher value always means clearer text. It looks at how many
dictionary senses the words have, how precise the vocabulary is, how many
vague words appear and how many sentences contain structurally ambiguous
patterns. It is most useful for comparing two versions of the same text.

## Install

Install the package from PyPI.

```bash
pip install clarity-score
```

The package needs Python 3.10 or newer.

## Download the language data

Download the language data once. The package uses the NLTK tokenizer and tagger and Open English WordNet.

```bash
python -m nltk.downloader punkt_tab averaged_perceptron_tagger_eng
python -m wn download oewn:2025
```

Open English WordNet 2025 is about 11 MB to download and takes about 105 MB on
disk. It is stored in the .wn_data directory in your home directory unless the
WN_DATA_DIR environment variable names another directory. The NLTK tokenizer
and tagger take about 22 MB on disk. They are stored in the nltk_data directory
in your home directory unless the NLTK_DATA environment variable names another
directory.

Clarity never downloads anything. When the data is missing, creating a Clarity
object raises LookupError with the two commands above, and the clarity-score
command prints them and exits with code 2.

The coherence signal of the lower level API is optional and needs an extra.

```bash
pip install "clarity-score[semantic-coherence]"
```

This extra installs sentence-transformers and PyTorch, and PyTorch is by far
the largest part of the install. The all-MiniLM-L6-v2 model adds about 90 MB on
top of PyTorch. It is downloaded from the Hugging Face Hub the first time a
MiniLMCoherenceScorer is created. On Linux, install the CPU build of PyTorch
first if you do not need GPU support.

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

The all extra installs every optional runtime feature.

```bash
pip install "clarity-score[all]"
```

## Quick start

Score a sentence or a whole document.

```python
from clarity_score import Clarity

clarity = Clarity()
scores = clarity.score("Replace the leaking kitchen faucet before Friday")

print(scores.clarity)
print(scores.to_dict())
```

Every score runs from 0 to 100 and a higher value always means clearer text. The clarity field is the headline score. It combines lexical clarity, which is high when words have few dictionary senses, specificity, which is high when the vocabulary is precise and free of vague words, and syntax, which is high when sentences avoid structurally ambiguous patterns. The readability field is the Flesch reading ease score and is reported next to the headline without changing it. The words field counts the words that were scored, so you can weight averages across many texts.

Create one Clarity object and reuse it. It can be shared between threads and passed to worker processes. Threads can share it only when clarity_score opens WordNet before your application uses the wn package itself, so create the Clarity object first or use processes. Text with no words of two or more letters scores 0 on every field.

Add words that count as vague in your own field.

```python
clarity = Clarity(extra_vague_words=["synergy", "leverage"])
```

Matching ignores case and extra spaces, and an entry can be a phrase of
several words. Entries are matched only against words made of letters, so an
entry that contains a hyphen, an apostrophe or a digit, such as cutting-edge,
never matches.

## What the score means

The clarity score is an uncalibrated heuristic. It has not been validated
against human judgments of clarity or against task success. Use it to compare
two versions of the same text, not to rank unrelated documents or to grade text
against a fixed bar.

```python
vague = clarity.score("We need to handle some stuff with the thing")
concrete = clarity.score("We need to replace the leaking kitchen faucet")
assert vague.clarity < concrete.clarity
```

The headline is 0.4 times lexical plus 0.4 times specificity plus 0.2 times
syntax. Lexical clarity and specificity are averaged over words and syntax is
averaged over sentences, so the headline does not depend on the length of the
text. A text and the same text repeated ten times get the same clarity.

Most real text scores near the middle of the range rather than near 100, so a
middling score is not a failing grade. If you gate a build on the score, choose
the threshold from the scores of your own documents. Compare texts of the same
kind, sentences with sentences and documents with documents.

The readability field is the Flesch reading ease score limited to the range 0
to 100. It measures sentence and word length, not ambiguity. Plain short
sentences often reach the top of its range.

## Limitations

The scorer works on English only. Text in other languages gets scores that
carry no meaning and are often higher than the scores of comparable English
text.

Words that are not in WordNet, such as product names, count as having a single
sense. They also count as general rather than specific words. Sense counts
ignore context, so common verbs such as run, set and check have many senses and
lower lexical clarity, while rare, technical, misspelled or made up words have
few senses and raise it. A string of rare nouns or of nonsense words can score
higher than a clear instruction.

Text with no words of two or more letters, such as an empty string, punctuation
or digits, scores 0 on every field and its words field is 0. Check words to
tell such text apart from unclear text.

Markdown markup is not counted as words, but the text of code blocks and YAML
front matter is scored like prose. Remove code blocks first if they should not
count. The clarity-score command removes front matter from files and standard
input, and Clarity.score does not.

Sentences are counted as runs of periods, question marks and exclamation marks.
A list of items without end punctuation counts as one sentence.

Python scores depend on the installed versions of Open English WordNet and the
NLTK models.

## Command line

Score a file from the command line and fail a build when the score is too low.

```bash
clarity-score SKILL.md --json --fail-under 40
```

The command removes YAML front matter from files before scoring. It exits with 1 when the score is below the threshold and with 2 when the input cannot be read.

The input is a file, a single hyphen for standard input, or the text to score.
`python -m clarity_score` runs the same command.

```bash
clarity-score "Click the Save button to store the file."
clarity-score - < SKILL.md
python -m clarity_score SKILL.md
```

The command prints one line for each field of ClarityScores, the field name
followed by its value. With `--json` it prints a JSON object with the same
keys as `ClarityScores.to_dict`, in the same order. `--fail-under` is compared
with the clarity field, with or without `--json`. Input with no words to score is
reported as skipped on standard error and exits with 0, even when
`--fail-under` is set.

The exit status is 0 on success, 1 when the clarity score is below
`--fail-under`, and 2 for a usage error, input that cannot be read or decoded
as UTF-8, or missing language data.

`clarity-score dir PATH` scores every file in a directory that matches
`--pattern`, which defaults to `**/SKILL.md`, and prints one line per file.
`--output` writes the results to a CSV file, or to a JSON file when the name
ends in `.json`. `--readability` adds the readability score and `--coherence`
adds the coherence score, which needs the semantic-coherence extra. This
subcommand reports the lower level `analyze` scores described below, not the
Clarity scores. It exits with 1 when the path is not a directory, no file
matches or a file fails to score. `clarity-score-dir` is an alias of
`clarity-score dir`. To score the word dir as text, pass it after `--`, as in
`clarity-score -- dir`.

## Use as an evaluation metric

Clarity works as a metric in evaluation frameworks without an adapter. Score
the text, compare the clarity field with a threshold and build the reason from
the fields of ClarityScores. The package depends on none of the frameworks
below, so install the one you use yourself.

Choose the threshold from a baseline of your own texts. One way is to score
texts you already accept and set the threshold just below the lowest of their
scores. You can also compare the score of a new version of a text with the
score of the old version instead of using a fixed bar. Do not divide the score
by 100 and gate at 0.5, a common default in evaluation frameworks. Most real
text scores near the middle of the range and many clear texts score below 50,
so that gate fails texts that are fine.

Output with no words to score gets 0 on every field and fails any threshold
above 0. Check the words field if empty output needs its own handling.

Clarity never downloads anything. A grader that runs without network access
needs the language data installed ahead of time with the commands in Download
the language data, for example when its image is built. Set NLTK_DATA and
WN_DATA_DIR when the data is not in the default directories.

The examples share these definitions. Create the Clarity object once and reuse
it for every sample.

```python
from clarity_score import Clarity, ClarityScores

clarity = Clarity()

# Set the threshold from the scores of your own baseline texts.
THRESHOLD = 40.0


def explain(scores: ClarityScores) -> str:
    return ", ".join(f"{name} {value}" for name, value in scores.to_dict().items())
```

A promptfoo Python assertion returns a pass flag, a score and a reason.
promptfoo reports scores from 0 to 1, so the score is divided by 100, while the
pass flag compares the clarity field with your threshold. Put the definitions
and this function in one file, such as clarity_assert.py.

```python
def get_assert(output, context):
    scores = clarity.score(output)
    return {
        "pass": scores.clarity >= THRESHOLD,
        "score": scores.clarity / 100,
        "reason": explain(scores),
    }
```

Reference the file from the assertions of a test.

```yaml
assert:
  - type: python
    value: file://clarity_assert.py
```

A DeepEval metric sets a score, a success flag and a reason. DeepEval also
reports scores from 0 to 1, so the metric reports the clarity field divided by
100 and takes its threshold on the same scale. DeepEval copies a metric by
passing its attributes back to the constructor, so the constructor stores the
threshold unchanged.

```py
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase


class ClarityMetric(BaseMetric):
    def __init__(self, threshold: float = THRESHOLD / 100):
        self.threshold = threshold

    def measure(self, test_case: LLMTestCase) -> float:
        scores = clarity.score(test_case.actual_output)
        self.score = scores.clarity / 100
        self.success = self.score >= self.threshold
        self.reason = explain(scores)
        return self.score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return self.success

    @property
    def __name__(self):
        return "Clarity"
```

An Inspect scorer returns the clarity field as the value of each sample, and
the mean metric averages it over the samples.

```py
from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState


@scorer(metrics=[mean()])
def clarity_scorer():
    async def score(state: TaskState, target: Target) -> Score:
        scores = clarity.score(state.output.completion)
        return Score(value=scores.clarity, explanation=explain(scores))

    return score
```

A pytest gate scores each file as its own test and shows every field when a
file falls below the threshold.

```python
from pathlib import Path

import pytest


@pytest.mark.parametrize("path", sorted(Path("prompts").glob("*.txt")), ids=str)
def test_prompt_is_clear(path):
    scores = clarity.score(path.read_text(encoding="utf-8"))
    assert scores.clarity >= THRESHOLD, explain(scores)
```

## Lower level API

The functions below return more detail than Clarity, such as each vague word
found, the ambiguous patterns and the WordNet data of each word. They are
outside the stability policy and may change in any minor release before 1.0.
Their scores differ from Clarity scores by design. `analyze` uses different
default weights and adds a document structure signal for text with more than
one line, so its `clarity_score` is not the Clarity headline.

```python
from clarity_score import ScoreWeights, analyze

result = analyze("The chef stirred the soup with the spoon.", include_readability=True)
print(result.clarity_score)
print(result.readability_score)
print([hit.phrase for hit in result.vague_hits])
print(result.to_dict())
```

`readability_score` maps the Flesch reading ease score onto the range 0 to 100,
so it is not the same number as the readability field of Clarity.
`readability_score` and `context_coherence` are reported next to
`clarity_score` and change it only when the readability or coherence weight of
`ScoreWeights` is above zero.

```python
weights = ScoreWeights(readability=0.2)
result = analyze(
    "The chef stirred the soup with the spoon.", include_readability=True, weights=weights
)
print(result.clarity_score)
```

For the coherence signal, install the semantic-coherence extra and pass a
`MiniLMCoherenceScorer` from `clarity_score.semantic_coherence` as
`coherence_scorer`. Unlike Clarity, `analyze` downloads the NLTK tokenizer and
tagger the first time it runs if they are missing. Open English WordNet is
never downloaded and must be installed first.

| Function | Purpose |
|----------|---------|
| `analyze(text)` | Detailed analysis of one text, returned as an `AnalysisResult` |
| `clarify(path)` | Score one file, every Markdown file in a directory, or the entries of a batch JSONL file |
| `extract_primitives(text)` | Compute every raw signal once for research on formulas |
| `apply_formula(primitives, weights)` | Combine raw signals with `FormulaWeights` |
| `analyze_lexical`, `analyze_syntax`, `find_vague_hits`, `tag_sentence` | The building blocks of the scores |

| Class | Description |
|-------|-------------|
| `AnalysisResult` | Result of `analyze` with every sub-score and report |
| `ScoreWeights` | Weights of the signals in the `analyze` formula |
| `ClarityPrimitives` | Every raw signal of one text |
| `LexicalReport` | WordNet sense counts and depths of the words |
| `SyntaxReport` | The structurally ambiguous patterns found |
| `VagueHit` | One vague word or phrase found in the text |

## Python and Rust differences

The clarity-score crate on crates.io offers the same Clarity interface in Rust.
Both packages return the same six fields with the same names, types, ranges and
direction, and both compute the headline with the same weights. Both give the
same all zero result for text with nothing to score and match vague words by
the same rules against the same built in list.

The two packages do not give equal numbers for the same text. They use
different part of speech taggers. The Rust crate embeds a table derived from
Open English WordNet and needs no download, while the Python package reads the
full lexicon through wn at run time. Scores from one package are not comparable
with scores from the other, so compare scores only within one package and
version. The lower level `analyze` functions differ more, because their default
weights differ and only the Python package scores document structure.

## Stability policy

From release 0.3.0 the following parts of the package are stable.

- The names Clarity, ClarityScores, score, extra_vague_words and to_dict.
- The six fields of ClarityScores with their names, order and types.
- The range 0 to 100 of every score, finite values, rounding to two decimals
  and the rule that a higher value always means clearer text.
- The meaning of each field, the headline as a weighted average of lexical,
  specificity and syntax without readability, and the all zero result with
  words equal to 0 for text with nothing to score.
- The exception types TypeError and LookupError.
- Both classes can be pickled, and ClarityScores is immutable and supports
  equality.
- The `--json` and `--fail-under` options of clarity-score, the `--json` keys,
  which equal the `to_dict` keys, and the exit codes 0, 1 and 2.

A minor release may add fields at the end of ClarityScores, new optional
keyword arguments and new command line options. Read fields by name, do not
build or unpack ClarityScores by position, and ignore unknown keys when you
read the JSON output.

Score values are not frozen. A minor release may change them when the vague
word list, the weights, the constants, the detectors or the bundled data
change. The changelog lists every such change under a Scoring changes heading.
A patch release never changes a score for the same input and the same data.

Before 1.0, removing or renaming a stable item or changing its type or meaning
takes at least one minor release with a DeprecationWarning and a Breaking entry
in the changelog. After 1.0 it takes a major release.

The repr text, the wording of error messages and performance are not promised.
Everything else the package exports is the lower level API and may change in
any minor release before 1.0.

## Development

From the root of a source checkout, change to the python directory and run the
tests there.

```bash
cd python
pip install -e ".[dev]"
python -m nltk.downloader punkt_tab averaged_perceptron_tagger_eng
python -m wn download oewn:2025
pytest
ruff check .
```

The coherence tests are skipped unless sentence-transformers is installed.

## Data and attribution

The package bundles no WordNet or NLTK data. At run time it reads Open English
WordNet 2025 from https://en-word.net, which you download with
`python -m wn download oewn:2025`. Open English WordNet is Copyright
2019-present The Open English WordNet Team and is licensed under CC BY 4.0,
https://creativecommons.org/licenses/by/4.0/. It is derived from Princeton
WordNet 3.0, Copyright 2006 by Princeton University. The package also uses the
NLTK `punkt_tab` tokenizer and `averaged_perceptron_tagger_eng` tagger models
from NLTK Data, which are distributed under their own licenses.

## License

clarity-score is licensed under either the MIT license or the Apache License,
Version 2.0, at your option. The license texts are in the `LICENSE-MIT` and
`LICENSE-APACHE-2.0` files. The `rust/NOTICE` file in the source repository
gives the full WordNet attribution and reproduces the Princeton WordNet 3.0
license.

Unless you explicitly state otherwise, any contribution intentionally
submitted for inclusion in the work by you, as defined in the Apache-2.0
license, shall be dual licensed as above, without any additional terms or
conditions.
