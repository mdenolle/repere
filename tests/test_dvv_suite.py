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
    from codameter import golden
    from codameter import use_cases as uc

    # split="all" so a stray FM_DVV_SPLIT can't filter the landslide case out
    # and make this fail spuriously.
    suite = dvv.DVVParamRecommendationSuite(split="all")
    # find the landslide item
    for _prompt, gold, scorer in suite.items():
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


def test_dvv_suites_are_registered_in_cli():
    # With codameter importable, the export-suite CLI must discover the dv/v
    # suites so `--suite dvv_processing.*` resolves.
    from frugalmind.cli import _all_registered_suites, _resolve_suites

    keys = {f"{s.dataset_id}.{s.suite_id}" for s in _all_registered_suites()}
    assert "dvv_processing.param_recommendation" in keys
    assert "dvv_processing.dvv_series" in keys
    picked = _resolve_suites(["dvv_processing.param_recommendation"])
    assert len(picked) == 1 and picked[0].suite_id == "param_recommendation"


def test_export_suite_writes_jsonl(tmp_path):
    from frugalmind.export import export_suites

    # split="all" pins the full corpus: without it the suite would honour
    # FM_DVV_SPLIT from the environment and the row count would no longer be
    # comparable to golden.CASES.
    suite = dvv.DVVParamRecommendationSuite(split="all")
    manifest = export_suites([suite], out_dir=tmp_path, version=dvv.VERSION)
    jsonl = tmp_path / "dvv_processing" / dvv.VERSION / "param_recommendation.jsonl"
    assert jsonl.exists()
    lines = jsonl.read_text().strip().splitlines()
    # One row per golden case (30 in the graded benchmark). Read the count
    # from codameter so a future change to the corpus does not break this.
    from codameter import golden

    assert len(lines) == len(golden.CASES)
    row = json.loads(lines[0])
    assert row["dataset_id"] == "dvv_processing"
    assert manifest  # sha256 manifest returned
