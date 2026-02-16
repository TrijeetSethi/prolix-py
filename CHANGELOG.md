# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `clarify()` takes `on_error="skip"` (the default) or `on_error="raise"`. With `"raise"`, directory and batch modes raise the first error from a file or entry instead of skipping it. Any other value raises `ValueError`
- `AnalysisResult.to_dict()` returns the result as a dict. `to_json()` returns the same dict and is kept for compatibility

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
- `clarity-score FILE` reads the file like `clarify()` and `clarity-score-dir` do, so front matter is stripped and a file gets the same score from every entry point
- Front matter no longer ends at a `---` inside a line such as `description: a---`, and a first line such as `--- not frontmatter` no longer opens a block. Inline `content` in a batch JSONL file now has its front matter stripped, as files already did
- Batch JSONL results from `clarify()` are keyed by the skill directory name when an entry's file is named `SKILL.md`, so a batch of `SKILL.md` files no longer collapses to one result. A key that is already taken falls back to the entry's `path`, so no result is overwritten. A relative `path` is read from the batch file's directory when the file exists there, and from the working directory otherwise
- `clarity-score-dir` no longer reports every file as failed and then crashes when stdout cannot encode non-ASCII characters, as with redirected output on Windows. A file is reported as an error only when scoring it fails
- `clarity-score-dir` scores every file that matches the pattern as one document, so `-p '*.jsonl'` or `-p '*.json'` no longer fails each file with `'dict' object has no attribute 'clarity_score'`
- The shipped type hints pass mypy, including on Python 3.10, and the package declares the `Typing :: Typed` classifier. The bundled vague word list is located with a call that Python 3.10 type stubs accept
- `analyze()` raises a `TypeError` that names the actual type when the text is not a `str`, such as bytes or `None`. Before, NLTK raised an unrelated regular expression error
- A single string passed as `extra_vague_words` to `analyze()` or `find_vague_hits()` counts as one entry. Before, it was split into characters and had no effect
- `ScoreWeights` raises `ValueError` when a weight is negative, NaN or infinite. Before, such a weight could make `analyze()` return a clarity score of 100. Setting every weight to 0 is still allowed and selects the unweighted mean of the signals
- `ScoreWeights.non_zero_weight_sum()` includes the structure weight, so it returns 0.80 for the defaults instead of 0.60. The module, `ScoreWeights` and `analyze()` docstrings now state the real default weights instead of 0.4, 0.4 and 0.2. Scores do not change

### Scoring changes
- The structure signal counts a sentence as an action sentence only when its first word is a listed action verb. Before, any first word of 3 or more letters counted, so descriptive prose and gibberish got full action credit. Prose that does not start with a listed verb now scores up to 5 points lower at the default weights. The list adds click, open, select, type, enter, press, go, choose, navigate, save, close, copy, paste, rename, move, sort, download, upload, fix, find, show and list. A sentence that starts with go, which has only 2 letters, now scores up to 5 points higher
- Headings, list items and sentences inside fenced code blocks no longer count toward the structure signal, so a `# comment` line in a shell example is not a heading. Code blocks are still counted
- `analyze()` and `extract_primitives()` compute `structural_clarity` only when the text, with leading and trailing whitespace removed, spans more than one line. For a single line it is `None` and its weight is shared among the other signals, so at the default weights the line scores with semantic 0.4, vagueness 0.4 and syntax 0.2, the blend the Rust crate uses. The one-line inputs in `fixtures/sentences.jsonl` score 4 to 12 points higher than with the structure signal

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
