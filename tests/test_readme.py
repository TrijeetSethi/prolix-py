"""Run the python code blocks of README.md so the examples cannot go stale."""

from __future__ import annotations

import re
from pathlib import Path

import nltk
import wn

README = Path(__file__).resolve().parents[1] / "README.md"

_PYTHON_BLOCK = re.compile(r"^```python\n(.*?)^```$", re.DOTALL | re.MULTILINE)


def _python_blocks() -> list[str]:
    return _PYTHON_BLOCK.findall(README.read_text(encoding="utf-8"))


def _refuse_download(*args: object, **kwargs: object) -> None:
    raise AssertionError("a README example tried to download data")


def test_readme_has_python_blocks():
    assert len(_python_blocks()) >= 2


def test_readme_python_blocks_run_without_downloading(monkeypatch):
    # The blocks run in order and share one namespace, as a reader runs them.
    monkeypatch.setattr(nltk, "download", _refuse_download)
    monkeypatch.setattr(wn, "download", _refuse_download)
    namespace: dict[str, object] = {"__name__": "readme"}
    for number, block in enumerate(_python_blocks(), start=1):
        exec(compile(block, f"README.md python block {number}", "exec"), namespace)
