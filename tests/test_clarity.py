"""Tests for the Clarity contract in clarity.py."""

from __future__ import annotations

import dataclasses
import doctest
import json
import math
import os
import pickle
import shutil
import subprocess
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import nltk
import pytest

from clarity_score import Clarity, ClarityScores, _nltk_data, lexical
from clarity_score import clarity as clarity_module

SRC = Path(__file__).resolve().parents[1] / "src"

KEYS = ["clarity", "lexical", "specificity", "syntax", "readability", "words"]
FLOAT_FIELDS = KEYS[:-1]

# Text with no word of two or more letters.
NOTHING_TO_SCORE = ["", "   ", "\n\t\r\n", "!!!", "1234 5678", "I", "a", "\U0001f642 \U0001f389"]

ODD_INPUTS = [
    *NOTHING_TO_SCORE,
    "Replace the faucet.\r\nThen test the valve.\r\n",
    "Tabs\tbetween\twords",
    "ﬁnd the ﬂag in the ﬁle",
    "Ship it \U0001f680 today",
    "x" * 5000,
    "Don't stop, it's fine and they'll know.",
    "Dr. Smith arrived at 5 p.m., e.g. after lunch.",
    "# Title\n\n- one item\n- two items\n\n```\ncode here\n```\n",
]


def _assert_valid(scores: ClarityScores) -> None:
    for name in FLOAT_FIELDS:
        value = getattr(scores, name)
        assert type(value) is float, name
        assert math.isfinite(value), name
        assert 0.0 <= value <= 100.0, name
        assert round(value, 2) == value, name
    assert type(scores.words) is int
    assert scores.words >= 0


def test_keys_follow_field_order():
    scores = Clarity().score("Replace the leaking kitchen faucet before Friday")
    assert [field.name for field in dataclasses.fields(ClarityScores)] == KEYS
    assert list(scores.to_dict()) == KEYS


def test_scores_are_finite_and_in_range(fixture_sentences):
    clarity = Clarity()
    texts = [row["sentence"] for row in fixture_sentences] + ODD_INPUTS
    for text in texts:
        _assert_valid(clarity.score(text))


@pytest.mark.parametrize("text", NOTHING_TO_SCORE)
def test_text_with_nothing_to_score_is_all_zero(text, capsys):
    scores = Clarity().score(text)
    assert scores == ClarityScores(
        clarity=0.0, lexical=0.0, specificity=0.0, syntax=0.0, readability=0.0, words=0
    )
    assert capsys.readouterr() == ("", "")


def test_fixture_pairs_order_as_expected(fixture_sentences):
    pairs: dict[str, dict[str, str]] = {}
    for row in fixture_sentences:
        expect = row.get("expect", {})
        if "pair_group" in expect:
            pairs.setdefault(expect["pair_group"], {})[expect["pair_role"]] = row["sentence"]
    assert pairs

    clarity = Clarity()
    for group, roles in pairs.items():
        low = clarity.score(roles["low"])
        high = clarity.score(roles["high"])
        assert low.clarity < high.clarity, group


@pytest.mark.parametrize("text", [b"Replace the faucet", None, 42, ["Replace the faucet"]])
def test_score_rejects_text_that_is_not_str(text):
    with pytest.raises(TypeError, match="text must be str"):
        Clarity().score(text)


def test_score_takes_text_by_position_only():
    with pytest.raises(TypeError):
        Clarity().score(text="Replace the faucet")


def test_constructor_takes_keywords_only():
    with pytest.raises(TypeError):
        Clarity(["synergy"])


def test_extra_vague_words_rejects_a_single_string():
    with pytest.raises(TypeError, match="not a single string"):
        Clarity(extra_vague_words="synergy")


@pytest.mark.parametrize("words", [["synergy", 3], [None], [b"synergy"]])
def test_extra_vague_words_rejects_items_that_are_not_str(words):
    with pytest.raises(TypeError, match="items must be str"):
        Clarity(extra_vague_words=words)


def test_extra_vague_words_ignore_case_and_extra_spaces():
    clarity = Clarity(extra_vague_words=["  Circle   BACK ", "synergy", "", "SYNERGY"])
    assert repr(clarity) == "Clarity(extra_vague_words=['circle back', 'synergy'])"

    text = "We circle back to the invoices every morning"
    assert clarity.score(text).specificity < Clarity().score(text).specificity


def test_missing_wordnet_raises_lookup_error(tmp_path):
    script = textwrap.dedent(
        """
        from clarity_score import Clarity

        try:
            Clarity()
        except LookupError as exc:
            print(exc)
        else:
            raise SystemExit("Clarity() did not raise LookupError")
        """
    )
    env = {**os.environ, "WN_DATA_DIR": str(tmp_path), "PYTHONPATH": str(SRC)}
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=120
    )
    assert proc.returncode == 0, proc.stderr
    # Every message names both commands, so check that WordNet is the data reported missing.
    assert "Open English WordNet 2025 is not installed" in proc.stdout
    assert "python -m wn download oewn:2025" in proc.stdout
    assert "python -m nltk.downloader punkt_tab averaged_perceptron_tagger_eng" in proc.stdout


def test_missing_nltk_data_raises_lookup_error_without_downloading(monkeypatch):
    def not_found(path):
        raise LookupError(path)

    def no_download(*args, **kwargs):
        raise AssertionError("Clarity() must not download")

    monkeypatch.setattr(nltk.data, "find", not_found)
    monkeypatch.setattr(nltk, "download", no_download)
    with pytest.raises(LookupError, match="python -m nltk.downloader punkt_tab") as info:
        Clarity()
    assert "python -m wn download oewn:2025" in str(info.value)


def test_nltk_data_left_as_zip_archives_is_found(tmp_path, monkeypatch):
    archives = ["tokenizers/punkt_tab.zip", "taggers/averaged_perceptron_tagger_eng.zip"]
    for name in archives:
        sources = [Path(base) / name for base in nltk.data.path]
        source = next((path for path in sources if path.is_file()), None)
        if source is None:
            pytest.skip(f"no {name} in the NLTK data path")
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, tmp_path / name)

    def no_download(*args, **kwargs):
        raise AssertionError("the NLTK data must be found without a download")

    monkeypatch.setattr(nltk.data, "path", [str(tmp_path)])
    monkeypatch.setattr(nltk, "download", no_download)
    monkeypatch.setattr(_nltk_data, "_ensured", False)
    clarity_module._require_resources()
    _nltk_data.ensure_nltk_data()


def test_one_instance_can_be_shared_between_threads(monkeypatch):
    texts = [
        f"The {noun} {verb} the {thing} with the {tool}."
        for noun in ["chef", "pilot", "gardener", "surgeon"]
        for verb, thing, tool in [
            ("stirred", "soup", "spoon"),
            ("repaired", "engine", "wrench"),
            ("trimmed", "hedge", "shears"),
            ("cleaned", "scalpel", "cloth"),
        ]
    ]
    clarity = Clarity()

    # An empty word cache makes every worker query WordNet itself.
    monkeypatch.setattr(lexical, "_word_cache", None)
    with ThreadPoolExecutor(max_workers=8) as pool:
        threaded = list(pool.map(clarity.score, texts))

    monkeypatch.setattr(lexical, "_word_cache", None)
    serial = [clarity.score(text) for text in texts]
    assert threaded == serial


def test_pickle_round_trip():
    # Pickling is how a Clarity object reaches multiprocessing workers.
    text = "Use synergy to grow the team"
    clarity = Clarity(extra_vague_words=["synergy"])
    restored = pickle.loads(pickle.dumps(clarity))
    assert repr(restored) == repr(clarity)
    assert restored.score(text) == clarity.score(text)

    scores = clarity.score(text)
    assert pickle.loads(pickle.dumps(scores)) == scores


def test_scores_are_immutable_and_hashable():
    scores = Clarity().score("Replace the leaking kitchen faucet")
    with pytest.raises(dataclasses.FrozenInstanceError):
        scores.clarity = 100.0
    assert hash(scores) == hash(dataclasses.replace(scores))


def test_to_dict_json_round_trip():
    scores = Clarity().score("Replace the leaking kitchen faucet before Friday")
    data = json.loads(json.dumps(scores.to_dict()))
    assert data == scores.to_dict()
    assert type(data["words"]) is int
    assert ClarityScores(**data) == scores


def test_docstring_examples():
    results = doctest.testmod(clarity_module)
    assert results.attempted > 0
    assert results.failed == 0
