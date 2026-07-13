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

# AstaBench-style category vocabularies; rows must use one of these.
VALID_OPENNESS = {
    "open-source-open-weight",
    "open-source-closed-weight",
    "closed-source-api",
    "closed-source-ui",
    "unknown",
}
VALID_TOOLSET = {"standard", "custom-interface", "custom", "unknown"}


def test_leaderboard_json_has_required_fields():
    payload = json.loads((SITE_DATA / "leaderboard.json").read_text())
    assert payload["schema_version"]
    assert payload["generated_at"]
    rows = payload["leaderboard"]
    assert rows, "leaderboard.json must contain at least one row"
    required = {
        "rank",
        "model_id",
        "agent_condition",
        "suite",
        "score",
        "cost_usd",
        "n_completed",
        "n_total",
        "openness",
        "toolset",
    }
    for row in rows:
        missing = required - set(row)
        assert not missing, f"row missing keys: {missing}"
        assert row["openness"] in VALID_OPENNESS, (
            f"row {row.get('rank')} model {row.get('model_id')!r}: "
            f"openness={row['openness']!r} not in {sorted(VALID_OPENNESS)}"
        )
        assert row["toolset"] in VALID_TOOLSET, (
            f"row {row.get('rank')} model {row.get('model_id')!r}: "
            f"toolset={row['toolset']!r} not in {sorted(VALID_TOOLSET)}"
        )


def test_skill_lift_json_has_required_fields_when_present():
    path = SITE_DATA / "skill_lift.json"
    if not path.exists():
        pytest.skip("skill_lift.json not present; export with scripts/build_site_data.py")
    payload = json.loads(path.read_text())
    assert payload.get("leaderboard_kind") == "skill_lift"
    rows = payload["rows"]
    assert rows, "skill_lift.json must contain at least one row when present"
    required = {
        "model_id",
        "suite",
        "skill_name",
        "skill_version",
        "score_none",
        "score_full",
        "lift",
        "cost_none_usd",
        "cost_full_usd",
        "n_total",
        "openness",
        "toolset",
    }
    for row in rows:
        missing = required - set(row)
        assert not missing, f"row missing keys: {missing}"
        assert row["lift"] == pytest.approx(row["score_full"] - row["score_none"], abs=1e-9)
        assert row["openness"] in VALID_OPENNESS
        assert row["toolset"] in VALID_TOOLSET


def test_html_selectors_exist_for_every_js_query():
    html = SITE_HTML.read_text()
    js = SITE_JS.read_text()
    ids = set(re.findall(r"querySelector\(['\"]#([\w-]+)['\"]\)", js))
    missing = [i for i in sorted(ids) if f'id="{i}"' not in html]
    assert not missing, f"HTML is missing IDs that JS queries: {missing}"


VALID_EVAL_CATEGORIES = {"document", "software-agent", "research-workflow"}


def test_rows_carry_an_eval_category():
    """The leaderboard filters on `category`; an untagged row would silently
    vanish from every filtered view."""
    for name, key in (("leaderboard.json", "leaderboard"), ("skill_lift.json", "rows")):
        path = SITE_DATA / name
        if not path.exists():
            continue
        rows = json.loads(path.read_text())[key]
        assert rows, f"{name} has no rows"
        for row in rows:
            assert row.get("category") in VALID_EVAL_CATEGORIES, (
                f"{name}: row {row.get('model_id')}/{row.get('suite')} has "
                f"category={row.get('category')!r}; expected one of "
                f"{sorted(VALID_EVAL_CATEGORIES)}"
            )


def test_js_knows_every_openness_and_category():
    """The chart's lookup tables are the contract between JSON values and what
    the tooltip/legend render. A value missing from the JS degrades silently to
    'unknown' — fail loudly instead."""
    js = SITE_JS.read_text()
    for key in VALID_OPENNESS - {"unknown"}:
        assert f'"{key}"' in js, f"app.js missing openness label for {key!r}"
    for key in VALID_EVAL_CATEGORIES:
        assert f'"{key}"' in js, f"app.js missing category entry for {key!r}"
    assert "OPENNESS_LABEL" in js
    assert "CATEGORIES" in js


def test_chart_exposes_csv_and_png_export():
    """Figures must be publication-ready: downloadable as data and as an image."""
    html = SITE_HTML.read_text()
    js = SITE_JS.read_text()
    assert 'id="dl-csv"' in html and 'id="dl-png"' in html
    assert "exportCsv" in js and "exportPng" in js
    # PNG export rasterises the SVG; without inlined CSS the image renders unstyled.
    assert "EXPORT_CSS" in js


def test_css_has_chart_and_category_classes():
    """The chart is hand-rolled SVG, so its styling lives in styles.css. A missing
    rule silently renders an unreadable figure rather than erroring."""
    css = (REPO_ROOT / "site" / "styles.css").read_text()
    for cls in (
        ".lift-line",   # the skill-lift connector — the core visual claim
        ".pt",          # markers
        ".gridline",
        ".axis-label",
        ".chip",        # category filters
        ".tag",         # eval tags
        "#tooltip",     # hover card (model version + weights)
    ):
        assert cls in css, f"styles.css missing rule for {cls}"


def test_site_uses_gaia_hazlab_palette():
    """The hub is a GAIA HazLab surface; keep it on the lab's tokens rather than
    drifting back to a bespoke theme."""
    css = (REPO_ROOT / "site" / "styles.css").read_text()
    assert "#4b2e83" in css, "UW Husky Purple (--purple) missing"
    assert "#2a1a4f" in css, "deep purple ink (--ink) missing"
    assert "Montserrat" in css and "Inter" in css
