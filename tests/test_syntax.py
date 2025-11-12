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
