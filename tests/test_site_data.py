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


def test_html_has_openness_and_toolset_columns():
    html = SITE_HTML.read_text()
    assert "<th scope=\"col\">Openness</th>" in html, (
        "main leaderboard / skill-lift tables must declare an Openness column"
    )
    assert "<th scope=\"col\">Toolset</th>" in html, (
        "main leaderboard / skill-lift tables must declare a Toolset column"
    )


def test_js_renders_pills_for_categories():
    js = SITE_JS.read_text()
    # Pill lookup tables are the contract between JSON values and CSS classes;
    # if a category disappears from the JS, the rendered cell silently falls
    # back to "unknown" — fail loudly instead.
    for key in VALID_OPENNESS - {"unknown"}:
        assert f'"{key}"' in js, f"app.js missing openness lookup for {key!r}"
    for key in VALID_TOOLSET - {"unknown"}:
        assert f'"{key}"' in js, f"app.js missing toolset lookup for {key!r}"
    # Each lookup table must reference appendPill so pills actually render.
    assert "appendPill" in js
    assert "OPENNESS_LABELS" in js
    assert "TOOLSET_LABELS" in js


def test_css_has_pill_classes():
    css = (REPO_ROOT / "site" / "styles.css").read_text()
    for cls in (
        ".pill",
        ".pill-open",
        ".pill-mixed",
        ".pill-closed",
        ".pill-unknown",
        ".pill-toolset-standard",
        ".pill-toolset-iface",
        ".pill-toolset-custom",
    ):
        assert cls in css, f"styles.css missing rule for {cls}"


# ---------------------------------------------------------------------------
# Pareto chart panel (P1.4)
# ---------------------------------------------------------------------------


def test_html_has_pareto_chart_panel():
    html = SITE_HTML.read_text()
    assert 'id="pareto"' in html, "index.html must declare a Pareto panel"
    assert 'id="pareto-canvas"' in html, "Pareto panel must include a <canvas id='pareto-canvas'>"
    assert "cdnjs.cloudflare.com/ajax/libs/Chart.js" in html, (
        "Chart.js must be loaded from the cdnjs allowlist"
    )


def test_app_js_exposes_pareto_helpers():
    js = SITE_JS.read_text()
    assert "function computeParetoFront" in js, (
        "app.js must define computeParetoFront — the Pareto computation is the "
        "non-trivial logic worth pinning"
    )
    assert "renderParetoChart" in js, "app.js must define renderParetoChart"
    # The chart wires into both the leaderboard rows and the canvas id.
    assert "#pareto-canvas" in js
    assert "Chart" in js  # references the Chart.js global


def test_app_js_uses_actual_css_variable_names_for_chart():
    """Chart colors must inherit from variables that exist in styles.css.

    The site theme defines `--text`, `--muted`, `--line` (not the
    Anthropic-design-system `--color-text-primary` family). Mismatched
    lookups produce silent fallbacks to dark text on a dark background.
    """
    js = SITE_JS.read_text()
    css = (REPO_ROOT / "site" / "styles.css").read_text()
    for var in ("--text", "--muted", "--line"):
        assert f'cssVar("{var}")' in js or f"cssVar('{var}')" in js, (
            f"app.js Pareto chart should read CSS variable {var}"
        )
        assert f"{var}:" in css, f"styles.css should define {var}"
    # And must not reference the old (non-existent) names.
    for ghost in ("--color-text-primary", "--color-text-secondary", "--color-border-tertiary"):
        assert ghost not in js, (
            f"app.js still references {ghost}, which is not defined in styles.css; "
            "switch to --text / --muted / --line"
        )


def test_app_js_passes_pareto_front_into_renderer():
    """`computeParetoFront` should be computed once in main() and reused by
    the renderer — duplicate work was flagged in P1.4 review."""
    js = SITE_JS.read_text()
    # The renderer accepts an optional front argument.
    assert "function renderParetoChart(rows, front)" in js, (
        "renderParetoChart must accept the pre-computed front as its second arg"
    )
    # main() should pass the front through.
    assert "renderParetoChart(leaderboardRows, paretoFront)" in js, (
        "main() must pass the pre-computed Pareto front into renderParetoChart"
    )


def test_app_js_clears_pareto_metadata_on_load_failure():
    """Error-path metadata fix from P1.4 review: catch block must update
    the Pareto panel's metadata spans, not leave them on 'Loading…'."""
    js = SITE_JS.read_text()
    # The catch block must touch the Pareto metadata spans.
    catch_start = js.find("} catch (error) {")
    assert catch_start != -1, "could not find catch block in main()"
    catch_block = js[catch_start:catch_start + 800]
    assert "paretoGeneratedAt" in catch_block, (
        "catch block must update #pareto-generated-at on failure"
    )
    assert "paretoSourceLabel" in catch_block, (
        "catch block must update #pareto-source-label on failure"
    )


def test_css_has_chart_wrap_rule():
    css = (REPO_ROOT / "site" / "styles.css").read_text()
    assert ".chart-wrap" in css, "styles.css missing .chart-wrap layout rule"
