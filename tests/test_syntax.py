import pytest

from clarity_score import analyze
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
