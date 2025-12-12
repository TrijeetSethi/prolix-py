"""Lazily ensures the NLTK resources this package needs are downloaded.

Mirrors the ``nltk.download(..., quiet=True)`` calls at the top of the
original starter.md script, but done once per process instead of on every
import.
"""

from __future__ import annotations

import nltk

_RESOURCES = (
    ("tokenizers/punkt_tab", "punkt_tab"),
    ("taggers/averaged_perceptron_tagger_eng", "averaged_perceptron_tagger_eng"),
)

_ensured = False


def ensure_nltk_data() -> None:
    global _ensured
    if _ensured:
        return
    for path, package in _RESOURCES:
        try:
            nltk.data.find(path)
        except LookupError:
            nltk.download(package, quiet=True)
    _ensured = True

__all__ = ["ensure_nltk_data"]
