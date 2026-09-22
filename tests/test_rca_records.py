"""RCA suite: schema, validator rules, checkers, cost layer (no Inspect needed)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from repere_suites.rca import SCHEMA_PATH, SEEDS_DIR, load_records
from repere_suites.rca.checkers import CheckOutcome, artifact_values, fdsn_records, staged_score
from repere_suites.rca.cost import load_price_map, price_usage
from repere_suites.rca.validate import load_record, rule_errors, validate_paths

# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------


def _seed_paths() -> list[Path]:
    return sorted(p for p in SEEDS_DIR.rglob("*.yaml") if not p.name.startswith("_"))


def test_seeds_exist_for_every_family():
    fams = {p.parent.name for p in _seed_paths()}
    assert fams == {"coding", "litreview", "sensor"}
    assert len(_seed_paths()) >= 15


def test_all_seeds_validate():
    n, problems = validate_paths(_seed_paths())
    assert n == len(_seed_paths())
    assert problems == [], "\n".join(problems)


def test_strict_mode_rejects_templates():
    _, problems = validate_paths(_seed_paths(), strict=True)
    assert any("R10" in p and "--strict" in p for p in problems)


def test_every_seed_is_a_template_with_todos():
    for p in _seed_paths():
        rec = load_record(p)
        assert rec["status"] == "template", p
        assert rec["todos"], p
        assert rec["provenance"]["author"] == "assistant-template", p


def test_schema_is_valid_json_schema():
    schema = json.loads(SCHEMA_PATH.read_text())
    assert schema["$schema"].endswith("2020-12/schema")
    assert set(schema["properties"]["tier"]["enum"]) == {
        "T1_physics",
        "T2_execution",
        "T3_reference",
        "T4_judgment",
    }


def test_load_records_filters():
    assert {r["family"] for r in load_records(family="coding")} == {"coding"}
    assert all(r["tier"] == "T2_execution" for r in load_records(tier="T2_execution"))
    assert load_records(ids=["rca-coding-qc-continuity-001"])[0]["group"] == "1b_qc"
    assert load_records(include_templates=False) == []


# ---------------------------------------------------------------------------
# Cross-field rules
# ---------------------------------------------------------------------------


@pytest.fixture
def qc_record() -> dict:
    return load_record(SEEDS_DIR / "coding" / "rca-coding-qc-continuity-001.yaml")


def _errs(rec: dict, **kw) -> list[str]:
    return rule_errors(rec, strict=False, base_dir=SEEDS_DIR / "coding", **kw)


def test_r02_tier_method_mismatch(qc_record):
    rec = copy.deepcopy(qc_record)
    rec["scoring"]["method"] = "retrieval_metrics"
    assert any(e.startswith("R02") for e in _errs(rec))


def test_r08_test_split_must_be_private(qc_record):
    rec = copy.deepcopy(qc_record)
    rec["holdout"]["split"] = "test"
    assert any(e.startswith("R08") for e in _errs(rec))


def test_r09_catalog_derived_needs_construction(qc_record):
    rec = copy.deepcopy(qc_record)
    rec["provenance"]["source_kind"] = "arcada_catalog"
    rec["holdout"]["construction"] = "none"
    assert any(e.startswith("R09") for e in _errs(rec))


def test_r10_verified_needs_zero_todos_and_human_author(qc_record):
    rec = copy.deepcopy(qc_record)
    rec["status"] = "verified"
    errs = _errs(rec)
    assert any("zero todos" in e for e in errs)
    assert any("named human author" in e for e in errs)


def test_r11_placeholder_doi_rejected(qc_record):
    rec = copy.deepcopy(qc_record)
    rec["provenance"]["source_ref"] = "10.0000/ooi-seed-001"
    assert any(e.startswith("R11") for e in _errs(rec))


def test_r13_hash_mismatch_detected(qc_record):
    rec = copy.deepcopy(qc_record)
    rec["inputs"]["files"][0]["sha256"] = "0" * 64
    assert any("sha256 mismatch" in e for e in _errs(rec))


# ---------------------------------------------------------------------------
# Checkers
# ---------------------------------------------------------------------------


class _Exec:
    def __init__(self, ok=True, artifacts=None):
        self.ok = ok
        self.artifacts = artifacts or {}


def test_artifact_values_partial_credit():
    out = artifact_values(
        _Exec(artifacts={"a": 1, "b": 2.0}),
        {"expected": {"a": 1, "b": 2.05, "c": 3}, "tolerances": {"b": {"abs": 0.1}}},
    )
    assert out.correct == pytest.approx(2 / 3)
    assert out.details["hits"] == {"a": True, "b": True, "c": False}


def test_fdsn_records_tolerance():
    ex = _Exec(artifacts={"trace_id": "OO.HYS14..BHZ", "sampling_rate_hz": 40.0, "n_samples": 4800})
    out = fdsn_records(
        ex,
        {
            "expected": {"trace_id": "OO.HYS14..BHZ", "sampling_rate_hz": 40.0, "n_samples": 4801},
            "tolerance_samples": 1,
        },
    )
    assert out.correct == 1.0


def test_staged_score_weights_and_gates():
    good = CheckOutcome(1.0, "ok")
    v, d = staged_score(
        code_extracted=True, ran_ok=True, artifacts={"x": 1}, artifact_keys=["x"], outcome=good
    )
    assert v == pytest.approx(1.0)
    v, _ = staged_score(
        code_extracted=True, ran_ok=True, artifacts={}, artifact_keys=["x"], outcome=good
    )
    assert v == pytest.approx(0.1), "missing artifact key must fail the runs and correct stages"
    v, _ = staged_score(
        code_extracted=False, ran_ok=False, artifacts={}, artifact_keys=["x"], outcome=None
    )
    assert v == 0.0
    with pytest.raises(ValueError):
        staged_score(
            code_extracted=True,
            ran_ok=True,
            artifacts={},
            artifact_keys=[],
            outcome=good,
            stage_weights={"code": 0.5, "runs": 0.5, "correct": 0.5},
        )


# ---------------------------------------------------------------------------
# Cost layer
# ---------------------------------------------------------------------------


def test_price_map_loads_and_flags():
    pm = load_price_map()
    assert pm.version
    p = price_usage(
        {"input_tokens": 1000, "output_tokens": 100},
        model_requested="anthropic/claude-haiku-4-5-20251001",
        model_reported="claude-haiku-4-5-20251001",
        price_map=pm,
    )
    assert p.card_id == "claude-haiku-4-5"
    assert p.model_unpinned is False
    assert p.cost_unverified is True and p.cost_usd is None, (
        "unverified cards are not priced by default"
    )
    p2 = price_usage(
        {"input_tokens": 1000, "output_tokens": 100},
        model_requested="anthropic/claude-haiku-4-5-20251001",
        model_reported=None,
        price_map=pm,
        allow_unverified=True,
    )
    assert p2.cost_usd == pytest.approx((1000 * 1.0 + 100 * 5.0) / 1e6)


def test_unknown_model_is_unpinned_and_unpriced():
    pm = load_price_map()
    p = price_usage(
        {"input_tokens": 10, "output_tokens": 10},
        model_requested="openai/gpt-999",
        model_reported=None,
        price_map=pm,
    )
    assert p.model_unpinned and p.cost_usd is None and p.card_id is None


def test_reported_model_drift_flags_unpinned():
    pm = load_price_map()
    p = price_usage(
        {},
        model_requested="anthropic/claude-sonnet-4-6",
        model_reported="claude-sonnet-4-6-20270101",
        price_map=pm,
        allow_unverified=True,
    )
    assert p.model_unpinned is True


def test_local_models_cost_zero():
    pm = load_price_map()
    p = price_usage(
        {"input_tokens": 5000, "output_tokens": 500},
        model_requested="ollama/qwen2.5:7b",
        model_reported=None,
        price_map=pm,
    )
    assert p.cost_usd == 0.0 and p.cost_unverified is False
    assert p.model_unpinned is True, "no weights digest recorded"
    p2 = price_usage(
        {},
        model_requested="ollama/qwen2.5:7b",
        model_reported=None,
        price_map=pm,
        local_digest="sha256:abc",
    )
    assert p2.model_unpinned is False
