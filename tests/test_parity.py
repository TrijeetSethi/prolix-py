"""Exercises the shared fixtures/sentences.jsonl corpus.

This file is also read by rust/tests/parity.rs. It's the cross-language
contract described in ARCHITECTURE.md decision #1: since the two
implementations are independent, we assert *relative* orderings and
threshold properties here rather than exact-float parity.
"""

from __future__ import annotations

from clarity_score.scoring import analyze

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
