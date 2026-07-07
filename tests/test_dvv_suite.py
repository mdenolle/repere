"""Smoke tests for the dv/v suite. Skipped unless codameter is installed."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("codameter", reason="dv/v suite needs codameter (pip install frugalmind[dvv])")

import frugalmind as F
from frugalmind_suites import dvv


def test_two_suites_with_expected_identity():
    assert len(dvv.ALL_SUITES) == 2
    for suite in dvv.ALL_SUITES:
        assert suite.task_kind == F.TaskKind.CODE_GENERATION
        assert suite.dataset_id == "dvv_processing"


def test_each_suite_yields_items_and_rows():
    for suite in dvv.ALL_SUITES:
        items = list(suite.items())
        rows = list(suite.export_rows())
        assert len(items) == len(rows) > 0
        prompt, gold, scorer = items[0]
        assert isinstance(prompt, str) and isinstance(gold, dict) and callable(scorer)
        # export_rows yields real BenchmarkRow instances, JSON-serializable.
        from dataclasses import asdict
        json.dumps(asdict(rows[0]))


def test_param_scorer_rewards_a_sound_config():
    from codameter import golden, use_cases as uc
    suite = dvv.DVVParamRecommendationSuite()
    # find the landslide item
    for (prompt, gold, scorer) in suite.items():
        if gold["use_case"] == "landslide":
            good = json.dumps(golden._jsonable(uc.recommend("landslide")))
            bad = json.dumps({"estimator": "stretching (TS)", "band": [0.4, 1.0],
                              "window": [10, 30]})
            assert scorer(good, gold) == pytest.approx(1.0)
            assert scorer(bad, gold) < 0.2
            break
    else:
        pytest.fail("no landslide item found")


def test_unknown_scorer_name_raises():
    with pytest.raises(ValueError):
        dvv.make_scorer_from_spec({"name": "nope"})
