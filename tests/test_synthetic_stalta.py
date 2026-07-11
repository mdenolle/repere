"""Tests for the Ridgecrest synthetic STA/LTA suite + detection_picks scorer."""

from __future__ import annotations

import pytest

from frugalmind import TaskKind
from frugalmind_suites.synthetic_stalta.items import SyntheticSTALTASuite
from frugalmind_suites.synthetic_stalta.scorers import (
    make_detection_picks_scorer,
    make_scorer_from_spec,
)


def test_detection_picks_matches_within_tolerance():
    scorer = make_detection_picks_scorer(tolerance_s=1.5)
    # exact
    assert scorer("[29.7]", [29.7]) == pytest.approx(1.0)
    # within tolerance
    assert scorer("[30.5]", [29.7]) == pytest.approx(1.0)
    # outside tolerance -> miss (F1 0)
    assert scorer("[40.0]", [29.7]) == 0.0


def test_detection_picks_negative_case_empty_is_perfect():
    scorer = make_detection_picks_scorer()
    # correct "no detection" on a negative case
    assert scorer("[]", []) == pytest.approx(1.0)
    assert scorer("No event detected.", []) == pytest.approx(1.0)
    # a false alarm on a negative case scores 0
    assert scorer("[15.0]", []) == 0.0


def test_detection_picks_two_events_f1():
    scorer = make_detection_picks_scorer(tolerance_s=1.5)
    # both found -> 1.0
    assert scorer("[29.7, 84.7]", [29.7, 84.7]) == pytest.approx(1.0)
    # one of two found -> P=1, R=0.5 -> F1=2/3
    assert scorer("[29.7]", [29.7, 84.7]) == pytest.approx(2 / 3)


def test_parse_prefers_json_array_over_prose():
    scorer = make_detection_picks_scorer()
    out = "After running STA/LTA the onset is at [29.8] seconds."
    assert scorer(out, [29.7]) == pytest.approx(1.0)


def test_spec_dispatch_and_unknown():
    scorer = make_scorer_from_spec(
        {"name": "detection_picks", "config": {"tolerance_s": 1.0}}
    )
    assert scorer("[29.7]", [29.7]) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="unknown scorer name"):
        make_scorer_from_spec({"name": "nope"})


def test_suite_loads_cases_and_scores_gold_perfectly():
    suite = SyntheticSTALTASuite(split="validation")
    rows = list(suite.export_rows())
    assert len(rows) >= 5
    n_pos = sum(1 for r in rows if r.metadata["expected_detection"])
    n_neg = len(rows) - n_pos
    assert n_pos >= 3 and n_neg >= 1  # positives + first-class negatives

    for r in rows:
        assert r.task_kind == TaskKind.EXTRACTION.value
        assert r.scorer_spec["name"] == "detection_picks"

    # feeding gold back as the model answer scores each case perfectly
    for prompt, gold, scorer in suite.items():
        import json

        assert scorer(json.dumps(gold), gold) == pytest.approx(1.0)
        assert "waveform =" in prompt
