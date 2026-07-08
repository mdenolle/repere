"""Tests for the Family-3 trajectory-DAG orchestration scorer."""

from __future__ import annotations

import json

import pytest

from frugalmind import TaskKind
from frugalmind_suites.orchestration.items import OrchestrationSuite
from frugalmind_suites.orchestration.scorers import (
    make_scorer_from_spec,
    make_trajectory_dag_scorer,
    make_trajectory_policy_scorer,
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


def test_duplicate_step_id_hard_fails():
    dup = {
        "calls": [
            {"id": "s1", "agent": "fetch_waveform", "deps": []},
            {"id": "s1", "agent": "detect", "deps": []},  # reused id
        ],
        "answer": "x",
    }
    assert _scorer()(json.dumps(dup), None) == 0.0


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


# --------------------------------------------------------------------------- #
# trajectory_policy — dynamic-workflow invariants
# --------------------------------------------------------------------------- #
# An adaptive trace: station A had low SNR (2.0) so a second fetch of a
# *different* station B (SNR 8.0) followed; both detections found events;
# locate fanned in; report drafted.
_ADAPTIVE = {
    "calls": [
        {
            "id": "s1",
            "agent": "fetch_waveform",
            "args": {"station": "A"},
            "deps": [],
            "obs": {"snr": 2.0},
        },
        {
            "id": "s2",
            "agent": "fetch_waveform",
            "args": {"station": "B"},
            "deps": [],
            "obs": {"snr": 8.0},
        },
        {"id": "s3", "agent": "detect", "deps": ["s2"], "obs": {"n_events": 1}},
        {"id": "s4", "agent": "detect", "deps": ["s1"], "obs": {"n_events": 1}},
        {"id": "s5", "agent": "locate", "deps": ["s3", "s4"], "obs": {"n_events": 1}},
        {"id": "s6", "agent": "draft_report", "deps": ["s5"], "obs": {}},
    ],
    "answer": "ok",
}

_PRECOND = {
    "type": "precondition",
    "agent": "locate",
    "requires_agent": "detect",
    "requires_obs": {"field": "n_events", "op": ">=", "value": 1},
    "min_count": 2,
}
_GUARD = {
    "type": "guard",
    "agent": "draft_report",
    "forbidden_when_agent": "locate",
    "forbidden_obs": {"field": "n_events", "op": "==", "value": 0},
}
_BRANCH = {
    "type": "branch",
    "when_agent": "fetch_waveform",
    "when_obs": {"field": "snr", "op": "<", "value": 3.0},
    "then_agent": "fetch_waveform",
    "then_args_differ_field": "station",
}


def test_policy_all_invariants_pass():
    scorer = make_trajectory_policy_scorer(rules=[_PRECOND, _GUARD, _BRANCH])
    assert scorer(json.dumps(_ADAPTIVE), None) == pytest.approx(1.0)


def _adaptive_with_one_empty_detection() -> dict:
    """_ADAPTIVE but s4's detection found no events, so only s3 satisfies the
    precondition — breaks it without leaving s5's dep on s4 dangling."""
    trace = json.loads(json.dumps(_ADAPTIVE))
    for c in trace["calls"]:
        if c["id"] == "s4":
            c["obs"] = {"n_events": 0}
    return trace


def test_policy_precondition_fails_without_enough_detections():
    # only one detection with events before locate -> min_count 2 fails
    scorer = make_trajectory_policy_scorer(rules=[_PRECOND])
    assert scorer(json.dumps(_adaptive_with_one_empty_detection()), None) == 0.0


def test_policy_guard_fails_when_reporting_on_empty_locate():
    empty = {
        "calls": [
            {"id": "a", "agent": "locate", "deps": [], "obs": {"n_events": 0}},
            {"id": "b", "agent": "draft_report", "deps": ["a"], "obs": {}},
        ],
        "answer": "x",
    }
    scorer = make_trajectory_policy_scorer(rules=[_GUARD])
    assert scorer(json.dumps(empty), None) == 0.0


def test_policy_branch_fails_without_adaptive_refetch():
    # low SNR but no second fetch of a different station -> branch fails
    static = {
        "calls": [
            {
                "id": "s1",
                "agent": "fetch_waveform",
                "args": {"station": "A"},
                "deps": [],
                "obs": {"snr": 2.0},
            },
            {"id": "s2", "agent": "detect", "deps": ["s1"], "obs": {"n_events": 0}},
        ],
        "answer": "x",
    }
    scorer = make_trajectory_policy_scorer(rules=[_BRANCH])
    assert scorer(json.dumps(static), None) == 0.0


def test_policy_recovery_passes_and_retry_storm_fails():
    rule = {
        "type": "recovery",
        "on_agent": "fetch_waveform",
        "error_field": "error",
        "then_agent": "fetch_waveform",
        "max_identical_retries": 1,
    }
    recovered = {
        "calls": [
            {
                "id": "s1",
                "agent": "fetch_waveform",
                "args": {"station": "A"},
                "deps": [],
                "obs": {"error": True},
            },
            {
                "id": "s2",
                "agent": "fetch_waveform",
                "args": {"station": "B"},
                "deps": [],
                "obs": {"snr": 9},
            },
        ],
        "answer": "x",
    }
    storm = {
        "calls": [
            {
                "id": "s1",
                "agent": "fetch_waveform",
                "args": {"x": 1},
                "deps": [],
                "obs": {"error": True},
            },
            {
                "id": "s2",
                "agent": "fetch_waveform",
                "args": {"x": 1},
                "deps": [],
                "obs": {"error": True},
            },
            {
                "id": "s3",
                "agent": "fetch_waveform",
                "args": {"x": 1},
                "deps": [],
                "obs": {"error": True},
            },
        ],
        "answer": "x",
    }
    scorer = make_trajectory_policy_scorer(rules=[rule])
    assert scorer(json.dumps(recovered), None) == pytest.approx(1.0)
    assert scorer(json.dumps(storm), None) == 0.0


def test_policy_termination_bounds_and_stop_condition():
    rule = {
        "type": "termination",
        "agent": "refine",
        "max_calls": 3,
        "stop_when_obs": {"field": "residual", "op": "<=", "value": 0.5},
    }
    stopped = {
        "calls": [
            {"id": "s1", "agent": "refine", "deps": [], "obs": {"residual": 0.9}},
            {"id": "s2", "agent": "refine", "deps": ["s1"], "obs": {"residual": 0.3}},
        ],
        "answer": "x",
    }
    kept_going = {
        "calls": [
            {"id": "s1", "agent": "refine", "deps": [], "obs": {"residual": 0.3}},
            {"id": "s2", "agent": "refine", "deps": ["s1"], "obs": {"residual": 0.2}},
        ],
        "answer": "x",
    }
    too_many = {
        "calls": [
            {"id": f"s{i}", "agent": "refine", "deps": [], "obs": {"residual": 0.9}}
            for i in range(4)
        ],
        "answer": "x",
    }
    scorer = make_trajectory_policy_scorer(rules=[rule])
    assert scorer(json.dumps(stopped), None) == pytest.approx(1.0)
    assert scorer(json.dumps(kept_going), None) == 0.0
    # 4 refine calls all with a unique id but > max_calls
    for i, c in enumerate(too_many["calls"]):
        c["id"] = f"r{i}"
    assert scorer(json.dumps(too_many), None) == 0.0


def test_policy_partial_fraction():
    # precondition fails (only one detection with events), branch passes -> 0.5
    trace = _adaptive_with_one_empty_detection()
    scorer = make_trajectory_policy_scorer(rules=[_PRECOND, _BRANCH])
    assert scorer(json.dumps(trace), None) == pytest.approx(0.5)


def test_policy_invalid_trace_and_unknown_rule():
    scorer = make_trajectory_policy_scorer(rules=[_GUARD])
    assert scorer("no json here", None) == 0.0
    cyclic = {
        "calls": [
            {"id": "a", "agent": "x", "deps": ["b"]},
            {"id": "b", "agent": "y", "deps": ["a"]},
        ],
    }
    assert scorer(json.dumps(cyclic), None) == 0.0
    with pytest.raises(ValueError, match="unknown policy rule type"):
        make_trajectory_policy_scorer(rules=[{"type": "nope"}])


def test_policy_spec_dispatch():
    spec = {
        "name": "trajectory_policy",
        "config": {"rules": [_PRECOND, _GUARD, _BRANCH]},
    }
    scorer = make_scorer_from_spec(spec)
    assert scorer(json.dumps(_ADAPTIVE), None) == pytest.approx(1.0)
