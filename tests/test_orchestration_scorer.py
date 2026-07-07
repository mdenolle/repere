"""Tests for the Family-3 trajectory-DAG orchestration scorer."""

from __future__ import annotations

import json

import pytest

from frugalmind import TaskKind
from frugalmind_suites.orchestration.items import OrchestrationSuite
from frugalmind_suites.orchestration.scorers import (
    make_scorer_from_spec,
    make_trajectory_dag_scorer,
)

# The reference DAG used across tests: 2 fetch -> 2 detect -> locate -> report.
_EXPECTED_AGENTS = ["fetch_waveform", "detect", "locate", "draft_report"]
_EXPECTED_EDGES = [
    ["fetch_waveform", "detect"],
    ["detect", "locate"],
    ["locate", "draft_report"],
]

_PERFECT = {
    "calls": [
        {"id": "s1", "agent": "fetch_waveform", "deps": []},
        {"id": "s2", "agent": "fetch_waveform", "deps": []},
        {"id": "s3", "agent": "detect", "deps": ["s1"]},
        {"id": "s4", "agent": "detect", "deps": ["s2"]},
        {"id": "s5", "agent": "locate", "deps": ["s3", "s4"]},
        {"id": "s6", "agent": "draft_report", "deps": ["s5"]},
    ],
    "answer": "report text",
}


def _scorer(**kw):
    return make_trajectory_dag_scorer(
        expected_agents=_EXPECTED_AGENTS,
        expected_edges=_EXPECTED_EDGES,
        **kw,
    )


def test_perfect_plan_scores_one():
    scorer = _scorer(max_calls=6)
    assert scorer(json.dumps(_PERFECT), None) == pytest.approx(1.0)


def test_prose_wrapped_json_is_parsed():
    scorer = _scorer(max_calls=6)
    out = f"Here is my plan:\n```json\n{json.dumps(_PERFECT)}\n```\nDone."
    assert scorer(out, None) == pytest.approx(1.0)


def test_missing_subagent_lowers_node_f1():
    # drop draft_report -> node recall 3/4, and the locate->report edge missing
    calls = [c for c in _PERFECT["calls"] if c["agent"] != "draft_report"]
    out = json.dumps({"calls": calls, "answer": "x"})
    score = _scorer(max_calls=6)(out, None)
    assert 0.0 < score < 1.0


def test_redundant_fanout_penalised_by_frugality():
    # 4 fetches instead of 2 -> 8 calls with max_calls 6 -> frugality 6/8
    extra = json.loads(json.dumps(_PERFECT))
    extra["calls"].extend(
        [
            {"id": "s7", "agent": "fetch_waveform", "deps": []},
            {"id": "s8", "agent": "fetch_waveform", "deps": []},
        ]
    )
    scorer = _scorer(max_calls=6)
    score = scorer(json.dumps(extra), None)
    # nodes + edges still perfect (1.0 each); frugality = 6/8 = 0.75
    expected = 0.4 * 1.0 + 0.4 * 1.0 + 0.2 * 0.75
    assert score == pytest.approx(expected)


def test_wrong_dependency_direction_lowers_edge_f1():
    # detect depends on locate (backwards) -> wrong agent edges
    bad = {
        "calls": [
            {"id": "s1", "agent": "fetch_waveform", "deps": []},
            {"id": "s2", "agent": "locate", "deps": ["s1"]},
            {"id": "s3", "agent": "detect", "deps": ["s2"]},
            {"id": "s4", "agent": "draft_report", "deps": ["s3"]},
        ],
        "answer": "x",
    }
    score = _scorer(max_calls=6)(json.dumps(bad), None)
    assert score < 1.0


def test_cycle_hard_fails():
    cyclic = {
        "calls": [
            {"id": "a", "agent": "fetch_waveform", "deps": ["b"]},
            {"id": "b", "agent": "detect", "deps": ["a"]},
        ],
        "answer": "x",
    }
    assert _scorer()(json.dumps(cyclic), None) == 0.0


def test_dangling_dependency_hard_fails():
    bad = {
        "calls": [{"id": "a", "agent": "detect", "deps": ["ghost"]}],
        "answer": "x",
    }
    assert _scorer()(json.dumps(bad), None) == 0.0


def test_unparseable_is_zero():
    assert _scorer()("I refuse to plan.", None) == 0.0
    assert _scorer()('{"no_calls_key": true}', None) == 0.0


def test_spec_dispatch_and_unknown():
    spec = {
        "name": "trajectory_dag",
        "config": {
            "expected_agents": _EXPECTED_AGENTS,
            "expected_edges": _EXPECTED_EDGES,
            "max_calls": 6,
        },
    }
    scorer = make_scorer_from_spec(spec)
    assert scorer(json.dumps(_PERFECT), None) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="unknown scorer name"):
        make_scorer_from_spec({"name": "nope"})


def test_suite_compose_export_and_items():
    suite = OrchestrationSuite(split="validation")
    rows = list(suite.export_rows())
    assert len(rows) == 1
    row = rows[0]
    assert row.task_kind == TaskKind.ORCHESTRATION.value
    assert row.scorer_spec["name"] == "trajectory_dag"
    assert row.metadata["max_calls"] == 6

    prompt, gold, scorer = next(iter(suite.items()))
    assert "JSON" in prompt or "json" in prompt
    # the suite's own reference plan scores perfectly against its scorer
    assert scorer(json.dumps(_PERFECT), gold) == pytest.approx(1.0)
