import time
from pathlib import Path

import pytest

from clarity_score import analyze, syntax
from clarity_score.syntax import analyze_syntax, tag_sentence


def test_pp_attachment_detected():
    tagged = tag_sentence("The chef stirred the soup with the spoon")
    report = analyze_syntax(tagged)
    assert any(hit.kind == "pp-attachment" for hit in report.hits)


def test_pp_attachment_classic_example():
    tagged = tag_sentence("I saw the man with the telescope")
    report = analyze_syntax(tagged)
    assert any(hit.kind == "pp-attachment" for hit in report.hits)


def test_no_pp_no_hit():
    tagged = tag_sentence("The cat slept")
    report = analyze_syntax(tagged)
    assert report.hits == []
    assert report.ambiguity_score == 0.0


def test_empty_token_list_gives_empty_report():
    report = analyze_syntax([])
    assert report.hits == []
    assert report.ambiguity_score == 0.0


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_text_writes_nothing_to_stdout(text, capsys):
    # The NLTK chunker prints a warning to stdout for every grammar stage
    # when it parses an empty token list.
    result = analyze(text)
    assert capsys.readouterr().out == ""
    assert result.syntax.hits == []


_SKILLS_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "skills"


def _whole_stream_hits(tagged):
    tree = syntax._chunker.parse(tagged)
    return [hit for detect in syntax._DETECTORS for hit in detect(tree)]


def test_segmented_hits_match_whole_stream_on_fixture_sentences(fixture_sentences):
    texts = [row["sentence"] for row in fixture_sentences]
    texts.append(". ".join(texts) + ".")
    for text in texts:
        tagged = tag_sentence(text)
        assert analyze_syntax(tagged).hits == _whole_stream_hits(tagged), text


@pytest.mark.parametrize("kind", ["specific", "vague"])
def test_segmented_hits_match_whole_stream_on_fixture_skills(kind):
    text = (_SKILLS_DIR / kind / "SKILL.md").read_text(encoding="utf-8")
    tagged = tag_sentence(text)
    assert analyze_syntax(tagged).hits == _whole_stream_hits(tagged)


def test_long_tagged_stream_is_linear():
    # Chunking 100,000 tokens as one stream takes several seconds and can
    # hit NLTK's regular-expression time limit. Chunking per sentence does not.
    sentence = [
        ("I", "PRP"), ("saw", "VBD"), ("the", "DT"), ("man", "NN"),
        ("with", "IN"), ("the", "DT"), ("telescope", "NN"), (".", "."),
    ]
    tagged = sentence * 12_500
    start = time.perf_counter()
    report = analyze_syntax(tagged)
    assert time.perf_counter() - start < 5.0
    assert len(report.hits) == 12_500
