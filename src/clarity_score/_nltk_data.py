"""Lazily ensures the NLTK resources this package needs are downloaded.

The check runs once per process, on first use instead of on every import.
"""

from __future__ import annotations

import nltk

# The trailing slash lets nltk.data.find also accept data left as zip archives,
# which is how the tokenizer and tagger load it.
_RESOURCES = (
    ("tokenizers/punkt_tab/", "punkt_tab"),
    ("taggers/averaged_perceptron_tagger_eng/", "averaged_perceptron_tagger_eng"),
)

_ensured = False


def ensure_nltk_data() -> None:
    """Download missing NLTK resources, or raise LookupError if that fails."""
    global _ensured
    if _ensured:
        return
    for path, package in _RESOURCES:
        try:
            nltk.data.find(path)
        except LookupError:
            nltk.download(package, quiet=True)
            try:
                nltk.data.find(path)
            except LookupError:
                raise LookupError(
                    f"NLTK data {package} is not installed and could not be downloaded. "
                    "Run: python -m nltk.downloader punkt_tab averaged_perceptron_tagger_eng"
                ) from None
    _ensured = True

__all__ = ["ensure_nltk_data"]
