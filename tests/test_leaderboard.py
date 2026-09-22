from __future__ import annotations

import json

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
    assert rows[0]["efficiency_score"] == 16.0
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
