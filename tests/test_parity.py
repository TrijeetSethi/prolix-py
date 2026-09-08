"""Check the shared fixtures/sentences.jsonl corpus.

rust/tests/parity.rs reads the same corpus and makes the same checks. The two
packages use different taggers and different copies of WordNet, so neither
suite compares scores across languages. Each suite checks that its own package
orders the two rows of each pair_group as expected and meets the threshold
expectations of each row.
"""

from __future__ import annotations

from clarity_score.readability import text_to_clarity_score
from clarity_score.scoring import analyze

# Every expect key that this suite and rust/tests/parity.rs check.
_EXPECT_KEYS = {
    "pair_group",
    "pair_role",
    "min_pp_attachment_hits",
    "max_pp_attachment_hits",
    "min_avg_senses",
    "min_readability_clarity",
    "max_readability_clarity",
}

_METRIC_BY_PAIR_GROUP = {
    "sandwich-specificity": lambda result: result.specificity,
    "vagueness": lambda result: result.clarity_score,
}


def test_pair_groups_order_as_expected(fixture_sentences):
    by_group: dict[str, dict[str, str]] = {}
    for row in fixture_sentences:
        expect = row.get("expect", {})
        group = expect.get("pair_group")
        if group:
            by_group.setdefault(group, {})[expect["pair_role"]] = row["sentence"]

    assert by_group, "expected at least one pair_group in the fixture corpus"

    for group, roles in by_group.items():
        assert "low" in roles and "high" in roles, f"incomplete pair for {group!r}"
        metric = _METRIC_BY_PAIR_GROUP[group]
        low_result = analyze(roles["low"])
        high_result = analyze(roles["high"])
        assert metric(low_result) < metric(high_result), (
            f"{group}: expected {roles['low']!r} < {roles['high']!r}"
        )


def test_pp_attachment_hit_counts(fixture_sentences):
    for row in fixture_sentences:
        expect = row.get("expect", {})
        result = None
        if "min_pp_attachment_hits" in expect:
            result = result or analyze(row["sentence"])
            hits = sum(1 for h in result.syntax.hits if h.kind == "pp-attachment")
            assert hits >= expect["min_pp_attachment_hits"], row["id"]
        if "max_pp_attachment_hits" in expect:
            result = result or analyze(row["sentence"])
            hits = sum(1 for h in result.syntax.hits if h.kind == "pp-attachment")
            assert hits <= expect["max_pp_attachment_hits"], row["id"]


def test_min_avg_senses(fixture_sentences):
    for row in fixture_sentences:
        expect = row.get("expect", {})
        if "min_avg_senses" in expect:
            result = analyze(row["sentence"])
            assert result.lexical.avg_senses >= expect["min_avg_senses"], row["id"]


def test_readability_thresholds(fixture_sentences):
    checked = 0
    for row in fixture_sentences:
        expect = row.get("expect", {})
        if "min_readability_clarity" in expect:
            score = text_to_clarity_score(row["sentence"])
            assert score >= expect["min_readability_clarity"], (row["id"], score)
            checked += 1
        if "max_readability_clarity" in expect:
            score = text_to_clarity_score(row["sentence"])
            assert score <= expect["max_readability_clarity"], (row["id"], score)
            checked += 1
    assert checked, "expected at least one readability expectation in the fixture corpus"


def test_every_expect_key_is_checked(fixture_sentences):
    for row in fixture_sentences:
        unknown = set(row.get("expect", {})) - _EXPECT_KEYS
        assert not unknown, f"{row['id']}: no test checks {sorted(unknown)}"
