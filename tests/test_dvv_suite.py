"""Smoke tests for the dv/v suite. Skipped unless codameter is installed."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("codameter", reason="dv/v suite needs codameter (pip install repere[dvv])")

import repere as F
from repere_suites import dvv


def test_two_suites_with_expected_identity():
    assert len(dvv.ALL_SUITES) == 2
    for suite in dvv.ALL_SUITES:
        assert suite.task_kind == F.TaskKind.CODE_GENERATION
        assert suite.dataset_id == "codameter"


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

    # split="all" so a stray FM_DVV_SPLIT can't filter the target case out and
    # make this fail spuriously.
    suite = dvv.DVVParamRecommendationSuite(split="all")
    # volcano is guaranteed present: as of codameter's hideable golden set
    # (v0.3.0), golden.CASES exposes only golden.PUBLIC_SAMPLE_IDS unless
    # CODAMETER_GOLDEN_DIR points at a private corpus, and "landslide" is not
    # in that public sample -- pick a use_case that actually is. Specifically
    # the *easy*-grade one ("easy-volcano-01"): the public sample's other two
    # use_cases (earthquake_fault, groundwater) are medium/hard grade, where a
    # generic uc.recommend() is not expected to clear the tighter RMS ceiling.
    target = "volcano"
    assert target in {c["use_case"] for c in golden.CASES}, (
        "expected use_case dropped out of golden.PUBLIC_SAMPLE_IDS; "
        "update this test to target one that's still present"
    )
    for _prompt, gold, scorer in suite.items():
        if gold["use_case"] == target:
            good = json.dumps(golden._jsonable(uc.recommend(target)))
            # A window past the recorded coda (no valid data -> NaN RMS -> score
            # 0.0): the easy grade isn't very band-sensitive (only the hard grade
            # is depth/frequency-dependent), so a merely mismatched band/window
            # like the old landslide-tuned "bad" config still scores near 1.0
            # here -- this one is unambiguously unsound instead.
            bad = json.dumps({"estimator": "stretching (TS)", "band": [0.4, 1.0],
                              "window": [80, 95]})
            assert scorer(good, gold) == pytest.approx(1.0)
            assert scorer(bad, gold) < 0.2
            break
    else:
        pytest.fail(f"no {target} item found")


def test_unknown_scorer_name_raises():
    with pytest.raises(ValueError):
        dvv.make_scorer_from_spec({"name": "nope"})


def test_dvv_suites_are_registered_in_cli():
    # With codameter importable, the export-suite CLI must discover the dv/v
    # suites so `--suite codameter.*` resolves.
    from repere.cli import _all_registered_suites, _resolve_suites

    keys = {f"{s.dataset_id}.{s.suite_id}" for s in _all_registered_suites()}
    assert "codameter.param_recommendation" in keys
    assert "codameter.dvv_series" in keys
    picked = _resolve_suites(["codameter.param_recommendation"])
    assert len(picked) == 1 and picked[0].suite_id == "param_recommendation"


def test_export_suite_writes_jsonl(tmp_path):
    from repere.export import export_suites

    # split="all" pins the full corpus: without it the suite would honour
    # FM_DVV_SPLIT from the environment and the row count would no longer be
    # comparable to golden.CASES.
    suite = dvv.DVVParamRecommendationSuite(split="all")
    manifest = export_suites([suite], out_dir=tmp_path, version=dvv.VERSION)
    jsonl = tmp_path / "codameter" / dvv.VERSION / "param_recommendation.jsonl"
    assert jsonl.exists()
    lines = jsonl.read_text().strip().splitlines()
    # One row per golden case (30 in the graded benchmark). Read the count
    # from codameter so a future change to the corpus does not break this.
    from codameter import golden

    assert len(lines) == len(golden.CASES)
    row = json.loads(lines[0])
    assert row["dataset_id"] == "codameter"
    assert manifest  # sha256 manifest returned
