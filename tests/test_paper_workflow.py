"""Tests for 'agentify the paper' — the research-workflow family (Family 3)."""

from __future__ import annotations

import json

import pytest

from frugalmind import TaskKind
from frugalmind_suites.orchestration.scorers import make_scorer_from_spec
from frugalmind_suites.paper_workflow.items import (
    PaperWorkflowSuite,
    load_ontology,
    operation_ids,
)


def _plan(nodes, edges):
    """Render a workflow as the JSON the orchestrator is asked to emit."""
    idx = {n: f"s{i}" for i, n in enumerate(nodes)}
    calls = [
        {"id": idx[n], "agent": n, "deps": [idx[a] for a, b in edges if b == n]}
        for n in nodes
    ]
    return json.dumps({"calls": calls})


def test_annotations_only_use_ontology_terms():
    """A term the model is never shown can never be matched, so an annotation
    outside the vocabulary is a silently-unscorable gold answer."""
    known = set(operation_ids())
    for p in PaperWorkflowSuite()._papers():
        for n in p["workflow"]["nodes"]:
            assert n in known, f"{p['id']}: {n!r} not in the ontology"


def test_reference_workflow_scores_perfectly_against_its_own_gold():
    """Self-consistency: if the author's own workflow does not score 1.0, the
    eval is broken before any model sees it."""
    suite = PaperWorkflowSuite()
    for p in suite._papers():
        _, gold, spec, _ = suite._compose(p)
        scorer = make_scorer_from_spec(spec)
        wf = p["workflow"]
        assert scorer(_plan(wf["nodes"], wf["edges"]), gold) == pytest.approx(1.0)


def test_invented_methodology_is_penalised():
    """The negative-case discipline, applied to research planning: padding the
    plan with impressive-sounding operations the paper never performed must cost
    precision."""
    suite = PaperWorkflowSuite()
    p = suite._papers()[0]
    _, gold, spec, _ = suite._compose(p)
    scorer = make_scorer_from_spec(spec)
    wf = p["workflow"]

    honest = scorer(_plan(wf["nodes"], wf["edges"]), gold)
    padded_nodes = [*wf["nodes"], "forward_model", "train_ml_model", "invert"]
    padded = scorer(_plan(padded_nodes, wf["edges"]), gold)
    assert padded < honest, "hallucinated methodology was not penalised"


def test_missing_fan_in_costs_edge_recall():
    """Collapsing a fan-in into a single chain is the dominant orchestration
    error; it must be visible in the score."""
    suite = PaperWorkflowSuite()
    p = suite._papers()[0]
    _, gold, spec, _ = suite._compose(p)
    scorer = make_scorer_from_spec(spec)
    wf = p["workflow"]

    full = scorer(_plan(wf["nodes"], wf["edges"]), gold)
    # drop every edge into the validation step -> the fan-in disappears
    thinned = [e for e in wf["edges"] if e[1] != "validate_against_reference"]
    assert scorer(_plan(wf["nodes"], thinned), gold) < full


def test_hard_tier_withholds_the_abstract():
    """The `hard` tier must make the model DESIGN the workflow, not extract it."""
    suite = PaperWorkflowSuite()
    p = dict(suite._papers()[0])
    p["tier"] = "hard"
    prompt, _, _, meta = suite._compose(p)
    assert meta["tier"] == "hard"
    assert "Abstract:" not in prompt
    assert "Title:" in prompt


def test_suite_exports_orchestration_rows():
    suite = PaperWorkflowSuite()
    rows = list(suite.export_rows())
    assert rows
    for r in rows:
        assert r.task_kind == TaskKind.ORCHESTRATION.value
        assert r.scorer_spec["name"] == "trajectory_dag"
        # every committed paper must be the PUBLIC (contaminated) split:
        # unpublished work is the hidden test split and never lives in git
        assert r.split == "validation" and r.visibility == "public"


def test_ontology_invariants_are_physically_sensible():
    onto = load_ontology()
    inv = {i["agent"]: i for i in onto["invariants"] if i["type"] == "precondition"}
    assert inv["preprocess_waveforms"]["requires_agent"] == "acquire_waveforms"
    assert inv["measure_dvv"]["requires_agent"] == "compute_correlation"
    assert inv["locate_events"]["requires_agent"] == "pick_phases"
