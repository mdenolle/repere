from __future__ import annotations

import json

import pytest

from repere.leaderboard import build_leaderboard, export_leaderboard


def test_build_leaderboard_ranks_by_score_then_cost():
    payload = build_leaderboard(
        [
            {
                "model_id": "expensive-good",
                "score": 0.8,
                "cost_usd": 0.2,
                "n_completed": 10,
                "n_total": 10,
            },
            {
                "model_id": "cheap-good",
                "agent_condition": "SeismoDataAgent+skill-v0.1-draft",
                "skill_name": "seismo-data-agent",
                "skill_version": "v0.1-draft",
                "score": 0.8,
                "cost_usd": 0.05,
                "n_completed": 10,
                "n_total": 10,
            },
            {
                "model_id": "cheap-weaker",
                "score": 0.7,
                "cost_usd": 0.01,
                "n_completed": 10,
                "n_total": 10,
            },
        ],
        generated_at="2026-05-08T00:00:00Z",
    )

    rows = payload["leaderboard"]
    assert [row["model_id"] for row in rows] == [
        "cheap-good",
        "expensive-good",
        "cheap-weaker",
    ]
    assert [row["rank"] for row in rows] == [1, 2, 3]
    assert payload["schema_version"] == "0.2"
    assert rows[0]["agent_condition"] == "SeismoDataAgent+skill-v0.1-draft"
    assert rows[0]["skill_name"] == "seismo-data-agent"
    assert rows[0]["skill_version"] == "v0.1-draft"
    assert rows[1]["agent_condition"] == "generic-coding-agent"
    assert payload["generated_at"] == "2026-05-08T00:00:00Z"


def test_export_leaderboard_reads_result_files(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "run.json").write_text(
        json.dumps(
            {
                "model_id": "stub-local",
                "score": 0.5,
                "cost_usd": 0.0,
                "n_completed": 3,
                "n_total": 6,
            }
        )
    )

    output = tmp_path / "site" / "data" / "leaderboard.json"
    export_leaderboard(results_dir, output)

    payload = json.loads(output.read_text())
    assert payload["leaderboard"][0]["model_id"] == "stub-local"
    assert payload["leaderboard"][0]["agent_condition"] == "generic-coding-agent"
    assert payload["leaderboard"][0]["suite"] == "sta_lta.intent_extraction"
    assert payload["leaderboard"][0]["run_file"] == "run.json"


# ---------------------------------------------------------------------------
# Schema v0.2: repeats, intervals, frontier flags
# ---------------------------------------------------------------------------


def test_a_single_run_gets_no_confidence_interval_and_says_so():
    """The regression that made every error bar on the site invisible.

    v0.1 reported a single run as a bare number. v0.2 reports `n_epochs = 1` and
    a null interval, so a renderer can tell "not measured" from "measured, zero
    variance", and the payload note tells a reader the same thing in words.
    """
    payload = build_leaderboard([{"model_id": "once", "score": 0.5, "cost_usd": 0.0}])
    row = payload["leaderboard"][0]
    assert row["n_epochs"] == 1
    assert row["score_ci95"] is None
    assert row["score_runs"] == [0.5]
    assert any("single run" in n for n in payload["notes"])


def test_repeats_produce_a_mean_and_an_interval():
    payload = build_leaderboard(
        [{"model_id": "five", "score_runs": [0.4, 0.5, 0.6, 0.5, 0.5], "cost_usd": 0.02}]
    )
    row = payload["leaderboard"][0]
    assert row["n_epochs"] == 5
    assert row["score_mean"] == pytest.approx(0.5)
    assert row["score_ci95"] > 0
    assert not any("single run" in n for n in payload["notes"])


def test_retired_v0_1_fields_are_gone():
    payload = build_leaderboard([{"model_id": "m", "score": 0.5, "cost_usd": 0.1}])
    row = payload["leaderboard"][0]
    for retired in ("score", "quality_percent", "efficiency_score"):
        assert retired not in row


def test_scoring_cost_is_kept_out_of_the_agent_cost():
    """Judging a run is not part of what the run costs to operate."""
    payload = build_leaderboard(
        [{"model_id": "m", "score": 0.9, "cost_usd": 0.02, "scoring_cost_usd": 0.0009}]
    )
    row = payload["leaderboard"][0]
    assert row["cost_usd"] == 0.02
    assert row["scoring_cost_usd"] == 0.0009


def test_tokens_travel_with_the_row_so_it_can_be_repriced():
    payload = build_leaderboard(
        [{"model_id": "m", "score": 0.9, "cost_usd": 0.02, "in_tokens": 1200, "out_tokens": 300}]
    )
    assert payload["leaderboard"][0]["total_tokens"] == 1500


def test_the_two_frontiers_are_flagged_separately():
    payload = build_leaderboard(
        [
            {
                "model_id": "free",
                "suite": "s",
                "score": 0.75,
                "cost_usd": 0.0,
                "in_tokens": 9000,
                "out_tokens": 0,
            },
            {
                "model_id": "cloud",
                "suite": "s",
                "score": 1.0,
                "cost_usd": 0.03,
                "in_tokens": 400,
                "out_tokens": 100,
            },
        ]
    )
    by_id = {r["model_id"]: r for r in payload["leaderboard"]}
    # Free and perfect-ish both sit on the dollar frontier...
    assert by_id["free"]["on_frontier_cost"] is True
    assert by_id["cloud"]["on_frontier_cost"] is True
    # ...but on tokens the free model is the expensive one, and drops off.
    assert by_id["cloud"]["on_frontier_tokens"] is True
    assert by_id["free"]["on_frontier_tokens"] is False


def test_perturbed_rows_do_not_compete_for_the_frontier():
    """A run under fault injection scores lower by construction."""
    payload = build_leaderboard(
        [
            {"model_id": "m", "suite": "s", "score": 0.9, "cost_usd": 0.05, "phase": "baseline"},
            {
                "model_id": "m",
                "suite": "s",
                "score": 0.4,
                "cost_usd": 0.001,
                "phase": "fault",
                "fault_rate": 0.2,
            },
        ]
    )
    by_phase = {r["phase"]: r for r in payload["leaderboard"]}
    assert by_phase["baseline"]["on_frontier_cost"] is True
    assert by_phase["fault"]["on_frontier_cost"] is False
    assert by_phase["fault"]["fault_rate"] == 0.2


def test_reliability_block_defaults_to_all_none_and_ignores_unknown_keys():
    payload = build_leaderboard(
        [
            {
                "model_id": "m",
                "score": 0.9,
                "cost_usd": 0.0,
                "reliability": {"consistency_outcome": 0.64, "not_a_metric": 1.0},
            }
        ]
    )
    rel = payload["leaderboard"][0]["reliability"]
    assert rel["consistency_outcome"] == 0.64
    assert rel["robust_fault"] is None
    assert "not_a_metric" not in rel


def test_the_frontier_is_computed_within_each_suite():
    """A 1.00 on an easy suite must not set the frontier for a hard one.

    `easy-win` is free and perfect on suite A. `hard-win` costs $0.03 and is the
    best anything achieves on suite B. Pooling the two suites into one hull
    would drop `hard-win` off the chart for being beaten by a free model on a
    different task, which is the mistake this guards against.

    `hard-mid` is the control: within suite B it costs more than `hard-free` and
    scores less than `hard-win`, so it is genuinely dominated and must be off.
    Note that `hard-free` *is* on the frontier — a free model scoring 0.10 is
    the best zero-dollar option available for that task, which is exactly what
    the frontier is for.
    """
    payload = build_leaderboard(
        [
            {"model_id": "easy-win", "suite": "A", "score": 1.0, "cost_usd": 0.0},
            {"model_id": "hard-win", "suite": "B", "score": 0.76, "cost_usd": 0.03},
            {"model_id": "hard-mid", "suite": "B", "score": 0.15, "cost_usd": 0.02},
            {"model_id": "hard-free", "suite": "B", "score": 0.10, "cost_usd": 0.0},
        ]
    )
    on = {r["model_id"] for r in payload["leaderboard"] if r["on_frontier_cost"]}
    assert "easy-win" in on
    assert "hard-win" in on, "a pooled hull would have dropped this"
    assert "hard-free" in on, "the best free option for its own task"
    assert "hard-mid" not in on, "dominated within its own suite"
