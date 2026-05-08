"""Smoke tests for the CLI subcommands that don't need a live provider."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frugalmind.cli import main


def test_smoke_eval_writes_json(tmp_path):
    results_dir = tmp_path / "results"
    rc = main(["smoke-eval", "--results-dir", str(results_dir)])
    assert rc == 0
    written = list(results_dir.glob("*.json"))
    assert written, "smoke-eval should write a JSON file"
    payload = json.loads(written[0].read_text())
    assert payload["model_id"] == "stub-local"
    assert payload["suite"] == "sta_lta.intent_extraction"


def test_export_leaderboard_writes_json(tmp_path):
    results_dir = tmp_path / "results"
    output = tmp_path / "site" / "data" / "leaderboard.json"
    main(["smoke-eval", "--results-dir", str(results_dir)])
    rc = main([
        "export-leaderboard",
        "--results-dir", str(results_dir),
        "--output", str(output),
    ])
    assert rc == 0
    payload = json.loads(output.read_text())
    assert payload["leaderboard"], "leaderboard payload must contain rows"
    assert payload["leaderboard"][0]["model_id"] == "stub-local"


def test_list_models_uses_default_registry(capsys):
    rc = main(["list-models"])
    assert rc == 0
    out = capsys.readouterr().out
    rows = json.loads(out)
    assert any(r["id"].startswith("claude-") for r in rows)
    assert any(r["tier"] == "cloud" for r in rows)


def test_list_skills_includes_manifest_entries(capsys):
    rc = main(["list-skills"])
    assert rc == 0
    out = capsys.readouterr().out
    rows = json.loads(out)
    names = {r["name"] for r in rows}
    assert {"stalta-detection", "obspy-fdsn-fetch", "seismic-plotting", "seismic-report"} <= names


def test_run_skill_lift_writes_payload(tmp_path):
    output = tmp_path / "skill_lift.json"
    rc = main(["run-skill-lift", "--skill", "stalta-detection", "--output", str(output)])
    assert rc == 0
    payload = json.loads(output.read_text())
    assert payload["leaderboard_kind"] == "skill_lift"
    assert payload["rows"][0]["skill_name"] == "stalta-detection"
