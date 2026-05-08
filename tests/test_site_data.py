"""Sanity tests for the static-site data files.

These tests validate that `site/data/leaderboard.json` and
`site/data/skill_lift.json` (when present) match the schema the HTML expects,
so a stale or malformed export is caught before deploy.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = REPO_ROOT / "site" / "data"
SITE_HTML = REPO_ROOT / "site" / "index.html"
SITE_JS = REPO_ROOT / "site" / "app.js"


def test_leaderboard_json_has_required_fields():
    payload = json.loads((SITE_DATA / "leaderboard.json").read_text())
    assert payload["schema_version"]
    assert payload["generated_at"]
    rows = payload["leaderboard"]
    assert rows, "leaderboard.json must contain at least one row"
    required = {
        "rank", "model_id", "agent_condition", "suite", "score",
        "cost_usd", "n_completed", "n_total",
    }
    for row in rows:
        missing = required - set(row)
        assert not missing, f"row missing keys: {missing}"


def test_skill_lift_json_has_required_fields_when_present():
    path = SITE_DATA / "skill_lift.json"
    if not path.exists():
        pytest.skip("skill_lift.json not present; export with scripts/build_site_data.py")
    payload = json.loads(path.read_text())
    assert payload.get("leaderboard_kind") == "skill_lift"
    rows = payload["rows"]
    assert rows, "skill_lift.json must contain at least one row when present"
    required = {
        "model_id", "suite", "skill_name", "skill_version",
        "score_none", "score_full", "lift",
        "cost_none_usd", "cost_full_usd", "n_total",
    }
    for row in rows:
        missing = required - set(row)
        assert not missing, f"row missing keys: {missing}"
        assert row["lift"] == pytest.approx(row["score_full"] - row["score_none"], abs=1e-9)


def test_html_selectors_exist_for_every_js_query():
    html = SITE_HTML.read_text()
    js = SITE_JS.read_text()
    ids = set(re.findall(r"querySelector\(['\"]#([\w-]+)['\"]\)", js))
    missing = [i for i in sorted(ids) if f'id="{i}"' not in html]
    assert not missing, f"HTML is missing IDs that JS queries: {missing}"
