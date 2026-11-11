# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - Unreleased

This is the first release published to PyPI. The version numbers 0.1.0 and
0.2.0 were used in the source repository but were never published, so the
entries below describe changes from the 0.2.0 source. From this release the
Python package and the Rust crate share one version number, because one
version number names one Clarity contract in both packages.

The package is published and imported as `prolix`, and its commands are
`prolix` and `prolix-dir`. In the source repository it was named
`clarity-score`, imported as `clarity_score`, with the commands
`clarity-score` and `clarity-score-dir`.

### Clarity contract
- `Clarity` and `ClarityScores` are the stable interface of the package. `Clarity().score(text)` returns a frozen `ClarityScores` with the fields `clarity`, `lexical`, `specificity`, `syntax`, `readability` and `words`, and `to_dict()` returns them in that order. Every float runs from 0 to 100, is rounded to two decimals and is higher for clearer text.
- `clarity` is 0.4 times `lexical` plus 0.4 times `specificity` plus 0.2 times `syntax`, and `readability` is the Flesch reading ease reported next to it. Text with no word of two or more letters scores 0 on every field.
- `Clarity(extra_vague_words=...)` adds vague words and phrases to the built in list. An entry is matched only against words made of letters, so an entry with a hyphen, an apostrophe or a digit, such as `cutting-edge`, never matches.
- Creating a `Clarity` never downloads anything and raises `LookupError` naming the install commands when the NLTK or WordNet data is missing. One `Clarity` object can be pickled and shared between threads, as long as it is created before the application opens WordNet through the `wn` package itself.
- Adding `Clarity` does not change `analyze()` scores, which differ from `Clarity` scores by design.
- `prolix` scores its input with `Clarity` and prints the six `ClarityScores` fields, one line per field with the field name followed by the value. `--json` prints an object with exactly the keys of `ClarityScores.to_dict()`, which are `clarity`, `lexical`, `specificity`, `syntax`, `readability` and `words`. `--fail-under` is compared with `clarity`. Before, the command printed `analyze()` results, which `prolix dir` still prints.
- The README states the stability policy. The names `Clarity`, `ClarityScores`, `score`, `extra_vague_words` and `to_dict`, the six fields with their order, types and range, the `--json` and `--fail-under` options, the `--json` keys and the exit codes 0, 1 and 2 are stable from this release. A minor release may change score values, and each such change is listed under Scoring changes with before and after values for `tests/fixtures/sentences.jsonl`. A patch release never changes a score for the same input and the same data.

### Scoring changes
- The structure signal counts a sentence as an action sentence only when its first word is a listed action verb. Before, any first word of 3 or more letters counted, so descriptive prose and gibberish got full action credit. Prose that does not start with a listed verb now scores up to 5 points lower at the default weights. The list adds click, open, select, type, enter, press, go, choose, navigate, save, close, copy, paste, rename, move, sort, download, upload, fix, find, show and list. A sentence that starts with go, which has only 2 letters, now scores up to 5 points higher.
- Headings, list items and sentences inside fenced code blocks no longer count toward the structure signal, so a `# comment` line in a shell example is not a heading. Code blocks are still counted.
- `analyze()` and `extract_primitives()` compute `structural_clarity` only when the text, with leading and trailing whitespace removed, spans more than one line. For a single line it is `None` and its weight is shared among the other signals, so at the default weights the line scores with semantic 0.4, vagueness 0.4 and syntax 0.2, the blend the Rust crate uses. The one-line inputs in `tests/fixtures/sentences.jsonl` score 4 to 12 points higher than with the structure signal. `prolix dir` leaves the `structural_clarity` cell of a single-line file empty in CSV output and omits the key in JSON output.
- `analyze()` and `extract_primitives()` match vague phrases over every word, including one-letter words, so the list entries `a lot` and `a bit` now match. A phrase no longer matches across punctuation, so `Choose the merge sort. Of the two outputs, keep the first.` no longer counts `sort of`. The vague ratio is still divided by the distinct words of two or more letters. An entry in `extra_vague_words` has runs of whitespace collapsed to one space, and an empty entry is ignored.
- `analyze()` and `extract_primitives()` clamp `semantic_ambiguity` to the range 0 to 100, as `ClarityPrimitives` documents, including the value from a custom `SemanticScorer`. Before, very polysemous short inputs went above 100 and lost more clarity. For example `Break cut.` had a `semantic_ambiguity` of 128.92 and now has 100, and its clarity score rises from 20.94 to 32.51.
- `analyze()` and `extract_primitives()` convert the text to Unicode NFC form and read typographic apostrophes (U+2018, U+2019 and U+02BC), double quotes (U+201C and U+201D) and hyphens (U+2010 and U+2011) as their ASCII forms before scoring, so text from a word processor scores the same as the same text typed in ASCII. Before, a curly apostrophe split `don’t` into `Don`, `’` and `t`, and an accented letter in decomposed form made its word drop out of the score. `AnalysisResult.sentence` keeps the text as given. `analyze()` and `Clarity` convert each `extra_vague_words` entry the same way, so an entry typed in decomposed form matches the same words as the text.
- `apply_formula()` divides by the weights of the signals that are present, as `analyze()` does, so a preset gives the same score as `analyze()` with the same weights. Before, a missing signal still counted in the divisor, so for example `EVEN_DISTRIBUTION_WEIGHTS`, whose coherence signal is not computed by default, scored about 8 points higher than `analyze()` with the same weights. `NO_STRUCTURE_WEIGHTS` and `VAGUENESS_HEAVY_WEIGHTS` now set structure to 0 instead of keeping the default 0.20.
- `apply_formula()` returns 0.0 for text with no word of two or more letters, such as `''`, `'!!!'` or `'42'`, as `analyze()` does. Before, it returned 60.0 for such text at the default weights. The `analyze()` and `apply_formula()` docstrings state this outcome.
- The Coleman-Liau index from `compute_readability_metrics()` counts letters only, as the formula defines. Before, it counted every non-whitespace character, so punctuation and digits raised it. The Automated Readability Index still counts every non-whitespace character, as textstat does. Clarity scores do not change.

The table gives `analyze(text).clarity_score` in the 0.2.0 source and in this
release, and `Clarity().score(text).clarity`, which is new in this release,
for each line of `tests/fixtures/sentences.jsonl`. The values were measured with
Open English WordNet 2025 (`oewn:2025`), NLTK 3.10.3 and wn 1.1.1.

| Fixture | analyze 0.2.0 | analyze 0.3.0 | Clarity 0.3.0 |
|---------|--------------:|--------------:|--------------:|
| `specificity-pair-low` | 26.33 | 25.11 | 25.11 |
| `specificity-pair-high` | 50.12 | 56.83 | 56.83 |
| `pp-attachment-1` | 47.02 | 52.69 | 49.69 |
| `pp-attachment-2` | 35.98 | 44.64 | 41.64 |
| `no-pp-attachment` | 47.62 | 53.49 | 53.49 |
| `vague-pair-low` | 30.75 | 37.67 | 34.67 |
| `vague-pair-high` | 45.92 | 57.90 | 57.90 |
| `polysemy-high` | 32.17 | 39.55 | 39.55 |
| `readability-easy-low-syllables` | 36.23 | 38.30 | 38.30 |
| `readability-hard-many-polysyllabic` | 46.91 | 52.54 | 52.54 |
| `readability-moderate` | 35.98 | 44.64 | 41.64 |
| `coherence-specific-high` | 50.12 | 56.83 | 56.83 |
| `coherence-incongruous-low` | 47.25 | 53.00 | 50.00 |
| `coherence-vague-vs-specific` | 29.75 | 29.66 | 26.66 |

### Added
- `clarify()` takes `weights`, `semantic_scorer` and `extra_vague_words` and passes them to `analyze()` for every file or entry it scores, in single file, directory and batch modes. Before, `clarify()` always scored with the defaults.
- `clarify()` takes `on_error="skip"` (the default) or `on_error="raise"`. With `"raise"`, directory and batch modes raise the first error from a file or entry instead of skipping it. Any other value raises `ValueError`.
- `AnalysisResult.to_dict()` returns the result as a dict. `to_json()` returns the same dict and is kept for compatibility.
- `AnalysisResult.word_count` is the number of scored words, the tokens of two or more letters, and `to_dict()` includes it as `word_count`. `ClarityPrimitives` has a matching `word_count` field at the end, which is `None` for a record written by an older version.
- `prolix dir PATH` scores every matching file in a directory, and `prolix-dir` stays as an alias of it. `python -m prolix` runs the `prolix` command, and every command takes `--version`.
- `prolix -` reads the text to score from standard input as UTF-8 and removes front matter as it does for a file.

### Changed
- The README and the package docstring lead with `Clarity`. The README says what the score means, lists its limitations, shows how to use `Clarity` as an evaluation metric, states the stability policy and attributes the Open English WordNet data. Every public class, method and function has a docstring.
- Cold WordNet lookups are several times faster because hypernym depth is memoized per synset. Scores do not change.
- `prolix` exits with code 2 and prints the reason on stderr when the input is a directory, names a missing `.md`, `.markdown` or `.txt` file, or cannot be read as UTF-8. Before, a directory or a missing file was scored as text and a non-UTF-8 file raised a traceback. Exit code 1 is left for a score below `--fail-under`.
- `prolix` reports input with no words to score as `skipped: no words to score` on stderr and exits with code 0, even when `--fail-under` is set. Such input prints no score lines, and with `--json` it prints the all zero record, as the Rust command does. An empty text argument is such input, as in the Rust command. Before, it printed a usage message and exited with code 1. A score below `--fail-under` prints a `fail:` line on stderr with and without `--json`.
- The default `prolix` command no longer takes `--readability` or `--coherence`, because the readability score is always printed and coherence is not part of `ClarityScores`. `prolix dir` keeps both options.
- The default `prolix` command no longer downloads NLTK data. When language data is missing it prints the install commands and exits with code 2.
- The installed `prolix` command runs `prolix.cli.main()`, so a first argument of `dir` or `compare` selects that subcommand. To score the word `dir` or `compare` itself, pass it after `--`, as in `prolix -- dir`.
- Front matter is stripped by one rule: the first line is exactly `---` and the block ends at the next line that is exactly `---`, with trailing spaces and tabs allowed on both lines. A leading byte order mark is ignored and CRLF line endings are accepted. Text with blank lines before the opening `---` is no longer treated as having front matter.
- In directory and batch modes `clarify()` logs a file or entry that fails to score as a warning on the `prolix.clarify` logger instead of printing to stderr. The file is still left out of the results, and the docstrings no longer promise a zero-score result for it.
- `prolix-dir` prints plain ASCII: `ok` and `error` instead of check marks, crosses and arrows, a line of hyphens above the summary, and no low variance hint.
- `FormulaWeights` no longer has the unused `_inverted_signals` field, so the constructor no longer accepts it. `apply_formula()` inverts readability, coherence and structure automatically, as before.
- `MiniLMCoherenceScorer` loads all-MiniLM-L6-v2 from a pinned Hugging Face Hub commit, so coherence scores do not change when the upstream model does. A new `revision` argument selects another commit, branch or tag. Other models still load their latest revision unless `revision` is given. The docstrings and the `semantic-coherence` extra state the model size as about 90 MB instead of 24 MB.
- The package requires nltk 3.9.1 or newer. With nltk 3.9.0, `import prolix` raises `LookupError` unless the NLTK wordnet corpus is installed.
- Building the package requires hatchling 1.27 or newer, the first version that writes the `License-Expression` and `License-File` metadata PyPI accepts. The two license classifiers are removed because the `MIT OR Apache-2.0` license expression replaces them.
- The `all` extra installs only runtime features, so it no longer installs pytest and ruff. The `readability` extra installs nothing, because readability metrics are always available, and is kept so that installs naming it keep working.
- The `dev` extra pins ruff 0.15.15, the version CI runs, so `ruff check .` gives the same result locally as in CI.

### Deprecated
- Model comparison is deprecated and will be removed in 0.4.0, because it is an experimental research tool. `prolix.compare_models()`, `prolix.model_compare.compare_models_benchmark()`, `prolix.cli.entry_compare()` and `python -m prolix.cli compare` still work and emit a `DeprecationWarning`. The `compare` subcommand of `prolix` also prints a `warning:` line on stderr, because Python does not show that warning to command line users by default.
- The `prolix-compare` command is no longer installed. `python -m prolix.cli compare` runs the same deprecated comparison.

### Fixed
- The first NLTK data check is done under a lock, so threads that score at the same time on a fresh process check and download the data once.
- `analyze()` can be called from several threads. WordNet access is serialized by a lock and the shared SQLite connection allows any thread. This sets `wn.config.allow_multithreading` for the whole process.
- Missing language data now raises one `LookupError` that names the install command (`python -m wn download oewn:2025`, or `python -m nltk.downloader punkt_tab averaged_perceptron_tagger_eng`), and a failed NLTK download is no longer treated as a success. The command line tools print that message on stderr and exit with code 2 instead of a traceback with code 1.
- NLTK tokenizer and tagger data installed only as zip archives is found, as NLTK itself loads it. Before, the package downloaded and unpacked that data again on first use, and reported it as missing when the download failed.
- Empty or whitespace-only text no longer makes NLTK print warnings to stdout, so `prolix --json` always prints valid JSON.
- Structural analysis runs in linear time on markdown with long runs of blank lines or spaces, which took minutes before. Heading and list markers now need a space or tab on the same line, so a bare `#`, `-` or `1.` followed by a line break is no longer counted.
- Syntax analysis chunks the tagged text one sentence at a time, so large documents no longer take quadratic time or raise NLTK's `TimeoutError`. Hits are identical to chunking the whole text at once, so scores do not change.
- Every text file is read and written as UTF-8, so a `SKILL.md` or batch JSONL file containing characters such as curly quotes no longer fails or decodes wrongly on Windows or under a non-UTF-8 locale. A leading byte order mark is ignored, so it no longer stops front matter from being stripped.
- `prolix --json --fail-under N` now exits with code 1 when the score is below N, as it already did without `--json`. Before, JSON mode always exited with code 0. `--fail-under` rejects `nan` and `inf` with a usage error and exit code 2, because a NaN threshold never failed.
- `prolix` scores a text argument longer than the file name limit (255 bytes on most systems) as text on Python 3.10 to 3.13. Before, checking whether the argument named a file raised `OSError: [Errno 36] File name too long`.
- `prolix FILE` reads the file like `clarify()` and `prolix-dir` do, so front matter is stripped the same way by every entry point.
- Front matter no longer ends at a `---` inside a line such as `description: a---`, and a first line such as `--- not frontmatter` no longer opens a block. Inline `content` in a batch JSONL file now has its front matter stripped, as files already did.
- `prolix` and `prolix dir` print no error when the program reading their output closes the pipe early, as `head` can, and this includes the output of `--help` and `--version` and stderr sent to the same pipe with `2>&1`. A command that has finished keeps its exit code, so a score below `--fail-under` still exits with code 1, and a command stopped while it is still writing exits with code 0. Before, they printed an ignored `BrokenPipeError` and exited with code 120. A command started with stdout closed, as with `>&-`, prints nothing on stdout and keeps its exit code.
- `prolix --help` prints a one-line description, examples and the exit codes instead of the module docstring run together into one paragraph. The `--readability` help of `prolix dir` no longer promises Flesch-Kincaid, Gunning Fog and SMOG, which are not printed, and its `--coherence` help says that coherence changes the score only when a coherence weight is set.
- Batch JSONL results from `clarify()` are keyed by the skill directory name when an entry's file is named `SKILL.md`, so a batch of `SKILL.md` files no longer collapses to one result. A key that is already taken falls back to the entry's `path`, so no result is overwritten. A relative `path` is read from the batch file's directory when the file exists there, and from the working directory otherwise.
- `prolix-dir` no longer reports every file as failed and then crashes when stdout cannot encode non-ASCII characters, as with redirected output on Windows. A directory or file name that stdout cannot encode is printed with backslash escapes. A file is reported as an error only when scoring it fails.
- `prolix-dir` scores every file that matches the pattern as one document, so `-p '*.jsonl'` or `-p '*.json'` no longer fails each file with `'dict' object has no attribute 'clarity_score'`.
- `analyze()` raises a `TypeError` that names the actual type when the text is not a `str`, such as bytes or `None`. Before, NLTK raised an unrelated regular expression error.
- A single string passed as `extra_vague_words` to `analyze()` or `find_vague_hits()` counts as one entry. Before, it was split into characters and had no effect.
- `ScoreWeights` raises `ValueError` when a weight is negative, NaN or infinite. Before, such a weight could make `analyze()` return a clarity score of 100. Setting every weight to 0 is still allowed and selects the unweighted mean of the signals.
- `ScoreWeights.non_zero_weight_sum()` includes the structure weight, so it returns 0.80 for the defaults instead of 0.60. The module, `ScoreWeights` and `analyze()` docstrings now state the real default weights instead of 0.4, 0.4 and 0.2. Scores do not change.
- `load_primitives()` closes the file it reads and ignores keys in `primitives` that are not `ClarityPrimitives` fields, so a file written by a newer version still loads. Before, an extra key raised `TypeError` and the file was left open. `ClarityPrimitives.from_dict()` sets a missing `readability_score`, `coherence` or `structural_clarity` to `None` instead of raising `KeyError`. The `save_primitives()` docstring shows the keys the code uses, `commit_hash` and `primitives`.
- The model comparison tooling reports correct statistics. Rank agreement is the number of concordant document pairs divided by concordant plus discordant pairs, leaving out tied pairs, so identical rankings give 100 and swapping the two models gives the same value. Before, identical rankings of 4 documents gave about 86 and swapping the models changed the result. `pearson_r_clarity` is not computed, so it is `None` (`null` in JSON) instead of a constant 0.0. `compare_models_benchmark()` scores each entry of a JSONL batch and accepts a single file instead of raising `UnboundLocalError`. `compare_models()` keys the results of the first entry, which is scored without a coherence model, as `"<baseline>"`, as its docstring says.
- `python -m prolix.cli compare --model NAME` compares only the named models. Before, each `--model` was added to the two default models. The command exits with code 1 and writes no output file when no comparison ran, as when sentence-transformers is not installed. Before, it exited with code 0.
- The shipped type hints pass mypy, including on Python 3.10, and the package declares the `Typing :: Typed` classifier. The bundled vague word list is located with a call that Python 3.10 type stubs accept.
- `prolix.__all__` lists `SyntaxReport`, which the package already imported.
- The sdist ships the tests and the shared test fixtures in `tests/fixtures`, so its tests run outside the source repository, and an sdist and a wheel can be built from an unpacked sdist.
- `LICENSE-APACHE-2.0` holds the canonical text of the Apache License 2.0.

### Known limitations
- The clarity score is an uncalibrated heuristic. It has not been validated against human judgments of clarity or against task success, so use it to compare two versions of the same text.
- The scorer works on English only. Text in other languages gets scores that carry no meaning.
- Words that are not in WordNet, such as product names, count as having a single sense and as general rather than specific words. Sense counts ignore context, so rare, misspelled or made up words raise lexical clarity.
- The text of code blocks and YAML front matter is scored like prose. The `prolix` command removes front matter from files and standard input, and `Clarity.score` does not.
- Sentences are counted as runs of periods, question marks and exclamation marks. A list of items without end punctuation counts as one sentence, and the dots in file names, version numbers and URLs count as sentence ends.
- Scores depend on the installed versions of Open English WordNet and the NLTK models. The Rust crate gives different numbers for the same text, so compare scores only within one package and version.
