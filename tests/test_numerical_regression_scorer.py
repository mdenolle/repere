"""Tests for the numerical-regression scorer and the pipeline_regression suite.

The metric functions are pure and tested directly. The end-to-end scorer runs
model-generated code through the host-Python sandbox (no Docker required, same
as ``tests/test_sta_lta_suite.py``) and reports a numeric artefact via
``record(...)``.
"""

from __future__ import annotations

import math

import pytest

from repere import TaskKind
from repere_suites.pipeline_regression.items import PipelineRegressionSuite
from repere_suites.pipeline_regression.scorers import (
    make_numerical_regression_scorer,
    make_scorer_from_spec,
    metric_allclose,
    metric_pearson,
    metric_pick_f1,
    metric_rmse,
)


# --------------------------------------------------------------------------- #
# Metric unit tests
# --------------------------------------------------------------------------- #
def test_pick_f1_perfect_and_empty():
    assert metric_pick_f1([1.0, 2.0], [1.0, 2.0], tolerance=0.5) == 1.0
    # empty vs empty == correct negative case
    assert metric_pick_f1([], [], tolerance=0.5) == 1.0
    # predicted picks where there should be none
    assert metric_pick_f1([1.0], [], tolerance=0.5) == 0.0
    # missed the only real pick
    assert metric_pick_f1([], [1.0], tolerance=0.5) == 0.0


def test_pick_f1_partial_and_tolerance():
    # 2 predicted, 2 gold, 1 matched within tolerance -> P=R=0.5 -> F1=0.5
    score = metric_pick_f1([1.0, 9.0], [1.2, 2.0], tolerance=0.5)
    assert math.isclose(score, 0.5, rel_tol=1e-9)
    # 2 predicted, 3 gold, 2 matched -> P=1.0, R=2/3 -> F1=0.8
    score2 = metric_pick_f1([1.0, 2.0], [1.0, 2.0, 8.0], tolerance=0.5)
    assert math.isclose(score2, 0.8, rel_tol=1e-9)
    # outside tolerance -> no match
    assert metric_pick_f1([1.0], [2.0], tolerance=0.5) == 0.0


def test_allclose_fraction_and_shape_mismatch():
    assert metric_allclose([1.0, 2.0], [1.0, 2.0], rtol=1e-3, atol=1e-6) == 1.0
    assert metric_allclose([1.0, 99.0], [1.0, 2.0], rtol=1e-3, atol=1e-6) == 0.5
    # shape mismatch -> 0
    assert metric_allclose([1.0], [1.0, 2.0], rtol=1e-3, atol=1e-6) == 0.0


def test_pearson_shape_and_scale_invariance():
    ref = [0.0, 1.0, 2.0, 3.0]
    assert math.isclose(metric_pearson([0.0, 2.0, 4.0, 6.0], ref), 1.0, rel_tol=1e-9)
    # anti-correlated clamps to 0
    assert metric_pearson([3.0, 2.0, 1.0, 0.0], ref) == 0.0


def test_rmse_score():
    assert metric_rmse([1.0, 1.0], [1.0, 1.0], rmse_scale=1.0) == 1.0
    # rmse == scale -> 0
    assert metric_rmse([2.0, 2.0], [1.0, 1.0], rmse_scale=1.0) == 0.0


def test_flatten_rejects_non_numeric():
    # a non-numeric leaf makes the metric return 0 rather than raising
    assert metric_allclose(["not a number"], [1.0], rtol=1e-3, atol=1e-6) == 0.0


# --------------------------------------------------------------------------- #
# End-to-end scorer through the host sandbox
# --------------------------------------------------------------------------- #
def _code(body: str) -> str:
    return f"```python\n{body}\n```"


def test_scorer_perfect_run():
    scorer = make_numerical_regression_scorer(
        artifact_key="p_picks",
        metric="pick_f1",
        required_calls=["record(p_picks"],
        tolerance=0.5,
    )
    out = _code("record(p_picks=[12.34, 41.87])")
    assert scorer(out, [12.34, 41.87]) == pytest.approx(1.0)


def test_scorer_runs_but_wrong_numbers_is_capped():
    scorer = make_numerical_regression_scorer(
        artifact_key="p_picks",
        metric="pick_f1",
        required_calls=["record(p_picks"],
        tolerance=0.5,
    )
    # code + calls + runs award 0.30; accuracy 0 -> total 0.30
    out = _code("record(p_picks=[999.0])")
    assert scorer(out, [12.34, 41.87]) == pytest.approx(0.30)


def test_scorer_no_code_is_zero():
    scorer = make_numerical_regression_scorer(artifact_key="p_picks", metric="pick_f1")
    assert scorer("I cannot help with that.", [1.0]) == 0.0


def test_scorer_missing_artifact_gets_partial_only():
    # runs fine but never records the expected key -> only code+calls credit
    scorer = make_numerical_regression_scorer(
        artifact_key="p_picks",
        metric="pick_f1",
        required_calls=["record(p_picks"],
    )
    out = _code("record(p_picks=[1.0])\nx = 1")  # calls present in source...
    # ...but rename the key so the artifact never appears
    out_wrong = _code("record(other=[1.0])")
    assert scorer(out, [1.0]) == pytest.approx(1.0)
    # calls substring absent, artifact absent -> only code stage (0.10)
    assert scorer(out_wrong, [1.0]) == pytest.approx(0.10)


# --------------------------------------------------------------------------- #
# Spec dispatch + suite integration
# --------------------------------------------------------------------------- #
def test_make_scorer_from_spec_roundtrip():
    spec = {
        "name": "numerical_regression",
        "config": {
            "artifact_key": "ccf",
            "metric": "pearson",
            "required_calls": ["record(ccf"],
        },
    }
    scorer = make_scorer_from_spec(spec)
    out = _code("record(ccf=[0.0, 1.0, 2.0, 3.0])")
    assert scorer(out, [0.0, 2.0, 4.0, 6.0]) == pytest.approx(1.0)


def test_make_scorer_from_spec_unknown_name():
    with pytest.raises(ValueError, match="unknown scorer name"):
        make_scorer_from_spec({"name": "nope"})


def test_sandbox_image_threads_but_host_backend_ignores_it():
    # A per-suite image is carried in the spec; on the default host backend it
    # is ignored, so scoring still succeeds. (The docker round-trip that would
    # actually use the image is covered by the docker-gated parity tests.)
    spec = {
        "name": "numerical_regression",
        "config": {
            "artifact_key": "p_picks",
            "metric": "pick_f1",
            "required_calls": ["record(p_picks"],
            "tolerance": 0.5,
            "sandbox_image": "ghcr.io/example/repere-sandbox-seisbench:latest",
        },
    }
    scorer = make_scorer_from_spec(spec)
    out = _code("record(p_picks=[1.0])")
    assert scorer(out, [1.0]) == pytest.approx(1.0)


def test_run_snippet_accepts_image_on_host_backend():
    from repere_suites.sta_lta.sandbox import run_snippet

    # image is accepted and ignored by the host backend (no docker requested).
    result = run_snippet(
        "record(x=1)", timeout_s=10, image="ghcr.io/example/whatever:latest"
    )
    assert result.ok
    assert result.artifacts.get("x") == 1


def test_load_pipelines_validates_required_keys(tmp_path, monkeypatch):
    # A row missing `tool` (used unconditionally by _compose) must raise an
    # actionable schema error at load time, not a late KeyError.
    import repere_suites.pipeline_regression.items as it

    bad = tmp_path / "pipelines.yaml"
    bad.write_text(
        "pipelines:\n"
        "  - id: x\n"
        "    label: no tool key\n"
        "    artifact_key: a\n"
        "    metric: allclose\n"
        "    gold: [1.0]\n"
        "    split: validation\n"
        "    visibility: public\n"
    )
    monkeypatch.setattr(it, "PIPELINES_PATH", bad)
    with pytest.raises(ValueError, match="missing key 'tool'"):
        it._load_pipelines()


def test_suite_carries_sandbox_image_in_spec():
    suite = PipelineRegressionSuite(split="validation")
    specs = {r.id: r.scorer_spec for r in suite.export_rows()}
    seis = specs["pipeline_regression/pipeline_regression/phasenet-p-picks-nc"]
    assert "seisbench" in seis["config"]["sandbox_image"]


def test_suite_compose_and_export():
    suite = PipelineRegressionSuite(split="validation")
    rows = list(suite.export_rows())
    assert len(rows) == 2
    ids = {r.id for r in rows}
    assert "pipeline_regression/pipeline_regression/phasenet-p-picks-nc" in ids
    for r in rows:
        assert r.task_kind == TaskKind.NUMERICAL_REGRESSION.value
        assert r.scorer_spec["name"] == "numerical_regression"
        assert r.scorer_spec["config"]["required_calls"][0].startswith("record(")

    # items() yields runnable (prompt, gold, scorer) triples
    triples = list(suite.items())
    assert len(triples) == 2
    prompt, gold, scorer = triples[0]
    assert "record(" in prompt
    assert callable(scorer)
