# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `Clarity` and `ClarityScores` are the stable interface of the package. `Clarity().score(text)` returns a frozen `ClarityScores` with the fields `clarity`, `lexical`, `specificity`, `syntax`, `readability` and `words`, and `to_dict()` returns them in that order. Every float runs from 0 to 100, is rounded to two decimals and is higher for clearer text. `clarity` is 0.4 times `lexical` plus 0.4 times `specificity` plus 0.2 times `syntax`, and `readability` is the Flesch reading ease reported next to it. Text with no word of two or more letters scores 0 on every field. `Clarity(extra_vague_words=...)` adds vague words and phrases to the built in list. Creating a `Clarity` never downloads anything and raises `LookupError` naming the install commands when the NLTK or WordNet data is missing. One `Clarity` object can be shared between threads and pickled. Scores from `analyze()` do not change and differ from `Clarity` scores by design
- `clarify()` takes `on_error="skip"` (the default) or `on_error="raise"`. With `"raise"`, directory and batch modes raise the first error from a file or entry instead of skipping it. Any other value raises `ValueError`
- `AnalysisResult.to_dict()` returns the result as a dict. `to_json()` returns the same dict and is kept for compatibility
- `AnalysisResult.word_count` is the number of scored words, the tokens of two or more letters, and `to_dict()` includes it as `word_count`. `ClarityPrimitives` has a matching `word_count` field at the end, which is `None` for a record written by an older version
- `clarity-score dir PATH` scores every matching file in a directory, and `clarity-score-dir` stays as an alias of it. `python -m clarity_score` runs the `clarity-score` command, and every command takes `--version`

### Changed
- Updated minimum Python version to 3.10 (using PEP 604 union syntax)
- Moved `import re` from function body to module level in scoring.py
- Added explicit `__all__` to all modules for better IDE/type-checker support
- Renamed entry point functions from `_entry_*` to `entry_*`
- Added `py.typed` marker for PEP 561 compliance
- Cold WordNet lookups are several times faster because hypernym depth is memoized per synset. Scores do not change
- `clarity-score` exits with code 2 and prints one `error:` line when the input is empty, is a directory, names a missing `.md`, `.markdown` or `.txt` file, or cannot be read as UTF-8. Before, a directory or a missing file was scored as text and a non-UTF-8 file raised a traceback. Exit code 1 is left for a score below `--fail-under`
- Front matter is stripped by one rule: the first line is exactly `---` and the block ends at the next line that is exactly `---`, with trailing spaces and tabs allowed on both lines. A leading byte order mark is ignored and CRLF line endings are accepted. Text with blank lines before the opening `---` is no longer treated as having front matter
- In directory and batch modes `clarify()` logs a file or entry that fails to score as a warning on the `clarity_score.clarify` logger instead of printing to stderr. The file is still left out of the results, and the docstrings no longer promise a zero-score result for it
- `clarity-score-dir` prints plain ASCII: `ok` and `error` instead of check marks, crosses and arrows, a line of hyphens above the summary, and no low variance hint
- `FormulaWeights` no longer has the unused `_inverted_signals` field, so the constructor no longer accepts it. `apply_formula()` inverts readability, coherence and structure automatically, as before
- `MiniLMCoherenceScorer` loads all-MiniLM-L6-v2 from a pinned Hugging Face Hub commit, so coherence scores do not change when the upstream model does. A new `revision` argument selects another commit, branch or tag. Other models still load their latest revision unless `revision` is given. The docstrings and the `semantic-coherence` extra state the model size as about 90 MB instead of 24 MB
- The package requires nltk 3.9.1 or newer. With nltk 3.9.0, `import clarity_score` raises `LookupError` unless the NLTK wordnet corpus is installed
- Building the package requires hatchling 1.27 or newer, the first version that writes the `License-Expression` and `License-File` metadata PyPI accepts. The two license classifiers are removed because the `MIT OR Apache-2.0` license expression replaces them
- The `all` extra installs only runtime features, so it no longer installs pytest and ruff. The `readability` extra installs nothing, because readability metrics are always available, and is kept so that installs naming it keep working
- The installed `clarity-score` command runs `clarity_score.cli.main()`, so a first argument of `dir` or `compare` selects that subcommand. To score the word `dir` or `compare` itself, pass it after `--`, as in `clarity-score -- dir`
- `clarity-score` scores its input with `Clarity` and prints the six `ClarityScores` fields, one line per field with the field name followed by the value. `--json` prints an object with exactly the keys of `ClarityScores.to_dict()`, which are `clarity`, `lexical`, `specificity`, `syntax`, `readability` and `words`. `--fail-under` is compared with `clarity`. Before, the command printed `analyze()` results, which `clarity-score dir` still prints
- `clarity-score -` reads the text to score from standard input as UTF-8 and removes front matter as it does for a file
- `clarity-score` reports input with no words to score as `skipped: no words to score` on stderr and exits with code 0, even when `--fail-under` is set. A score below `--fail-under` prints a `fail:` line on stderr with and without `--json`
- The default `clarity-score` command no longer takes `--readability` or `--coherence`, because the readability score is always printed and coherence is not part of `ClarityScores`. `clarity-score dir` keeps both options
- The default `clarity-score` command no longer downloads NLTK data. When language data is missing it prints the install commands and exits with code 2

### Deprecated
- Model comparison is deprecated and will be removed in 0.4.0, because it is an experimental research tool. `clarity_score.compare_models()`, `clarity_score.model_compare.compare_models_benchmark()`, `clarity_score.cli.entry_compare()` and `python -m clarity_score.cli compare` still work and emit a `DeprecationWarning`. The `compare` subcommand of `clarity-score` also prints a `warning:` line on stderr, because Python does not show that warning to command line users by default

### Removed
- The `clarity-score-compare` command is no longer installed. `python -m clarity_score.cli compare` runs the same deprecated comparison

### Fixed
- Removed duplicate `_score_file` function in clarify.py (S-01)
- Fixed hatch build packages path (`src/clarity_score` → `clarity_score`)
- Ensured package data files (`vague_words.txt`, `py.typed`) are included in wheel
- Empty or whitespace-only text no longer makes NLTK print warnings to stdout, so `clarity-score --json` always prints valid JSON
- `analyze()` can be called from several threads: WordNet access is serialized by a lock and the shared SQLite connection allows any thread. This sets `wn.config.allow_multithreading` for the whole process
- Missing language data now raises one `LookupError` that names the install command (`python -m wn download oewn:2025`, or `python -m nltk.downloader punkt_tab averaged_perceptron_tagger_eng`), and a failed NLTK download is no longer treated as a success. The command line tools print that message on stderr and exit with code 2 instead of a traceback with code 1
- Structural analysis runs in linear time on markdown with long runs of blank lines or spaces, which took minutes before. Heading and list markers now need a space or tab on the same line, so a bare `#`, `-` or `1.` followed by a line break is no longer counted
- Syntax analysis chunks the tagged text one sentence at a time, so large documents no longer take quadratic time or raise NLTK's `TimeoutError`. Hits are identical to chunking the whole text at once, so scores do not change
- Every text file is read and written as UTF-8, so a `SKILL.md` or batch JSONL file containing characters such as curly quotes no longer fails or decodes wrongly on Windows or under a non-UTF-8 locale. A leading byte order mark is ignored, so it no longer stops front matter from being stripped
- `clarity-score --json --fail-under N` now exits with code 1 when the score is below N, as it already did without `--json`. Before, JSON mode always exited with code 0
- `clarity-score` scores a text argument longer than the file name limit (255 bytes on most systems) as text on Python 3.10 to 3.13. Before, checking whether the argument named a file raised `OSError: [Errno 36] File name too long`
- `clarity-score FILE` reads the file like `clarify()` and `clarity-score-dir` do, so front matter is stripped the same way by every entry point
- Front matter no longer ends at a `---` inside a line such as `description: a---`, and a first line such as `--- not frontmatter` no longer opens a block. Inline `content` in a batch JSONL file now has its front matter stripped, as files already did
- Batch JSONL results from `clarify()` are keyed by the skill directory name when an entry's file is named `SKILL.md`, so a batch of `SKILL.md` files no longer collapses to one result. A key that is already taken falls back to the entry's `path`, so no result is overwritten. A relative `path` is read from the batch file's directory when the file exists there, and from the working directory otherwise
- `clarity-score-dir` no longer reports every file as failed and then crashes when stdout cannot encode non-ASCII characters, as with redirected output on Windows. A file is reported as an error only when scoring it fails
- `clarity-score-dir` scores every file that matches the pattern as one document, so `-p '*.jsonl'` or `-p '*.json'` no longer fails each file with `'dict' object has no attribute 'clarity_score'`
- The shipped type hints pass mypy, including on Python 3.10, and the package declares the `Typing :: Typed` classifier. The bundled vague word list is located with a call that Python 3.10 type stubs accept
- `analyze()` raises a `TypeError` that names the actual type when the text is not a `str`, such as bytes or `None`. Before, NLTK raised an unrelated regular expression error
- A single string passed as `extra_vague_words` to `analyze()` or `find_vague_hits()` counts as one entry. Before, it was split into characters and had no effect
- `ScoreWeights` raises `ValueError` when a weight is negative, NaN or infinite. Before, such a weight could make `analyze()` return a clarity score of 100. Setting every weight to 0 is still allowed and selects the unweighted mean of the signals
- `ScoreWeights.non_zero_weight_sum()` includes the structure weight, so it returns 0.80 for the defaults instead of 0.60. The module, `ScoreWeights` and `analyze()` docstrings now state the real default weights instead of 0.4, 0.4 and 0.2. Scores do not change
- `apply_formula()` divides by the weights of the signals that are present, as `analyze()` does, so a preset gives the same score as `analyze()` with the same weights. Before, a missing signal still counted in the divisor, so for example `EVEN_DISTRIBUTION_WEIGHTS`, whose coherence signal is not computed by default, scored about 8 points higher than `analyze()` with the same weights. `NO_STRUCTURE_WEIGHTS` and `VAGUENESS_HEAVY_WEIGHTS` now set structure to 0 instead of keeping the default 0.20
- The Coleman-Liau index from `compute_readability_metrics()` counts letters only, as the formula defines. Before, it counted every non-whitespace character, so punctuation and digits raised it. The Automated Readability Index still counts every non-whitespace character, as textstat does. Clarity scores do not change
- `load_primitives()` closes the file it reads and ignores keys in `primitives` that are not `ClarityPrimitives` fields, so a file written by a newer version still loads. Before, an extra key raised `TypeError` and the file was left open. `ClarityPrimitives.from_dict()` sets a missing `readability_score`, `coherence` or `structural_clarity` to `None` instead of raising `KeyError`. The `save_primitives()` docstring shows the keys the code uses, `commit_hash` and `primitives`
- The model comparison tooling reports correct statistics. Rank agreement is the number of concordant document pairs divided by concordant plus discordant pairs, leaving out tied pairs, so identical rankings give 100 and swapping the two models gives the same value. Before, identical rankings of 4 documents gave about 86 and swapping the models changed the result. `pearson_r_clarity` is not computed, so it is `None` (`null` in JSON) instead of a constant 0.0. `compare_models_benchmark()` scores each entry of a JSONL batch and accepts a single file instead of raising `UnboundLocalError`. `compare_models()` keys the results of the first entry, which is scored without a coherence model, as `"<baseline>"`, as its docstring says
- `clarity-score-compare --model NAME` compares only the named models. Before, each `--model` was added to the two default models, so the README example scored each model twice. The command exits with code 1 and writes no output file when no comparison ran, as when sentence-transformers is not installed. Before, it exited with code 0
- `apply_formula()` returns 0.0 for text with no word of two or more letters, such as `''`, `'!!!'` or `'42'`, as `analyze()` does. Before, it returned 60.0 for such text at the default weights. The `analyze()` and `apply_formula()` docstrings state this outcome
- `clarity-score --help` prints a one-line description, examples and the exit codes instead of the module docstring run together into one paragraph. The `--readability` help no longer promises Flesch-Kincaid, Gunning Fog and SMOG, which are not printed, and the `--coherence` help says that coherence changes the score only when a coherence weight is set
- NLTK tokenizer and tagger data installed only as zip archives is found, as NLTK itself loads it. Before, the package downloaded and unpacked that data again on first use, and reported it as missing when the download failed
- `clarity-score` and `clarity-score dir` print no error when the program reading their output closes the pipe early, as `head` can, and this includes the output of `--help` and `--version` and stderr sent to the same pipe with `2>&1`. A command that has finished keeps its exit code, so a score below `--fail-under` still exits with code 1, and a command stopped while it is still writing exits with code 0. Before, they printed an ignored `BrokenPipeError` and exited with code 120. A command started with stdout closed, as with `>&-`, prints nothing on stdout and keeps its exit code

### Scoring changes
- The structure signal counts a sentence as an action sentence only when its first word is a listed action verb. Before, any first word of 3 or more letters counted, so descriptive prose and gibberish got full action credit. Prose that does not start with a listed verb now scores up to 5 points lower at the default weights. The list adds click, open, select, type, enter, press, go, choose, navigate, save, close, copy, paste, rename, move, sort, download, upload, fix, find, show and list. A sentence that starts with go, which has only 2 letters, now scores up to 5 points higher
- Headings, list items and sentences inside fenced code blocks no longer count toward the structure signal, so a `# comment` line in a shell example is not a heading. Code blocks are still counted
- `analyze()` and `extract_primitives()` compute `structural_clarity` only when the text, with leading and trailing whitespace removed, spans more than one line. For a single line it is `None` and its weight is shared among the other signals, so at the default weights the line scores with semantic 0.4, vagueness 0.4 and syntax 0.2, the blend the Rust crate uses. The one-line inputs in `fixtures/sentences.jsonl` score 4 to 12 points higher than with the structure signal. `clarity-score dir` leaves the `structural_clarity` cell of a single-line file empty in CSV output and omits the key in JSON output
- `analyze()` and `extract_primitives()` match vague phrases over every word, including one-letter words, so the list entries `a lot` and `a bit` now match. A phrase no longer matches across punctuation, so `Choose the merge sort. Of the two outputs, keep the first.` no longer counts `sort of`. The vague ratio is still divided by the distinct words of two or more letters. An entry in `extra_vague_words` has runs of whitespace collapsed to one space, and an empty entry is ignored
- `analyze()` and `extract_primitives()` clamp `semantic_ambiguity` to the range 0 to 100, as `ClarityPrimitives` documents, including the value from a custom `SemanticScorer`. Before, very polysemous short inputs went above 100 and lost more clarity. For example `Break cut.` had a `semantic_ambiguity` of 128.92 and now has 100, and its clarity score rises from 20.94 to 32.51
- `analyze()` and `extract_primitives()` convert the text to Unicode NFC form and read typographic apostrophes (U+2018, U+2019 and U+02BC), double quotes (U+201C and U+201D) and hyphens (U+2010 and U+2011) as their ASCII forms before scoring, so text from a word processor scores the same as the same text typed in ASCII. Before, a curly apostrophe split `don’t` into `Don`, `’` and `t`, and an accented letter in decomposed form made its word drop out of the score. `AnalysisResult.sentence` keeps the text as given

## [0.2.0] — 2025-09-24

### Added
- Structural clarity signal (`structure.py`) — measures heading hierarchy, list density, code block presence, and action-verb ratio
- Primitives-first architecture (`primitives.py`) — `extract_primitives()` computes all signals once; `apply_formula()` applies N formula presets instantly
- `compare_models()` convenience function for benchmarking coherence models
- `_discover_directory()`, `_discover_batch_jsonl()` made available in clarify module's public API
- `save_primitives()` and `load_primitives()` JSONL helpers

### Changed
- Default weights redistributed: structure now has 0.20 weight, and semantic, vagueness and syntax were reduced to 0.24, 0.24 and 0.12. The defaults add up to 0.80, and the formula divides by the sum of the weights in use, so they act as 0.30, 0.30, 0.15 and 0.25
- Readability formula improved: `to_clarity_score()` uses sqrt scaling for better differentiation
- Vague word penalty normalized: capped at 40% based on unique-word ratio (was unbounded)
- Syntax penalty normalized: per-sentence rate, capped at 10 points

## [0.1.0] — Initial Release

### Added
- Core scoring pipeline: `analyze()` function combining syntactic, lexical, and vagueness signals
- WordNet polysemy scoring via Open English WordNet (oewn:2025)
- Syntactic ambiguity detection (PP attachment patterns)
- Vague-word lexicon matching (multi-word phrases supported)
- Readability formulas: Flesch-Kincaid, Gunning Fog, SMOG, ARI, Coleman-Liau
- Semantic coherence scoring via MiniLM embeddings (optional feature)
- CLI tools: `clarity-score`, `clarity-score-dir`, `clarity-score-compare`
- Clarify workflow: single file, directory scan, batch JSONL

### Dependencies
- nltk>=3.9 (POS tagging, tokenization)
- wn>=1.0 (Open English WordNet access)
