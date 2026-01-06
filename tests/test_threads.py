"""Tests that analyze() can be called from several threads."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor
from itertools import product
from pathlib import Path

from clarity_score import analyze, lexical

SRC = Path(__file__).resolve().parents[1] / "src"

_SUBJECTS = ["The chef", "A pilot", "The gardener", "Our librarian", "The surgeon"]
_ACTIONS = [
    "stirred the soup with the spoon",
    "repaired the engine before noon",
    "planted tulips near the fence",
    "catalogued rare manuscripts",
    "sharpened the scalpel carefully",
    "painted the barn red",
    "measured the depth of the river",
    "folded the maps neatly",
    "tuned the old piano",
    "watered the orchids every morning",
]
SENTENCES = [f"{subject} {action}." for subject, action in product(_SUBJECTS, _ACTIONS)]


def test_threaded_analyze_matches_serial(monkeypatch):
    # An empty word cache makes every worker query WordNet itself.
    monkeypatch.setattr(lexical, "_word_cache", None)
    with ThreadPoolExecutor(max_workers=8) as pool:
        threaded = list(pool.map(analyze, SENTENCES))

    monkeypatch.setattr(lexical, "_word_cache", None)
    serial = [analyze(sentence) for sentence in SENTENCES]

    assert len(SENTENCES) == 50
    assert threaded == serial


def test_main_thread_works_after_first_use_in_worker_thread():
    # A fresh interpreter, so that the first WordNet use happens in a worker.
    script = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(SRC)!r})
        from concurrent.futures import ThreadPoolExecutor
        from clarity_score import analyze

        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(analyze, "The chef stirred the soup.").result()
        print(analyze("A cartographer surveyed the glacier.").clarity_score)
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr
    assert 0.0 <= float(proc.stdout.strip()) <= 100.0
