# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Updated minimum Python version to 3.10 (using PEP 604 union syntax)
- Moved `import re` from function body to module level in scoring.py
- Added explicit `__all__` to all modules for better IDE/type-checker support
- Renamed entry point functions from `_entry_*` to `entry_*`
- Added `py.typed` marker for PEP 561 compliance

### Fixed
- Removed duplicate `_score_file` function in clarify.py (S-01)
- Fixed hatch build packages path (`src/clarity_score` → `clarity_score`)
- Ensured package data files (`vague_words.txt`, `py.typed`) are included in wheel
- Empty or whitespace-only text no longer makes NLTK print warnings to stdout, so `clarity-score --json` always prints valid JSON

## [0.2.0] — 2025-09-24

### Added
- Structural clarity signal (`structure.py`) — measures heading hierarchy, list density, code block presence, and action-verb ratio
- Primitives-first architecture (`primitives.py`) — `extract_primitives()` computes all signals once; `apply_formula()` applies N formula presets instantly
- `compare_models()` convenience function for benchmarking coherence models
- `_discover_directory()`, `_discover_batch_jsonl()` made available in clarify module's public API
- `save_primitives()` and `load_primitives()` JSONL helpers

### Changed
- Default weights redistributed: structure now has 0.20 weight; semantic/vagueness reduced to maintain total=1.0
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
