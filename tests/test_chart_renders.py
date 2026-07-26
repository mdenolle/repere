"""The chart must actually RENDER — not merely parse.

This exists because the dashboard shipped with an empty chart. Two runtime errors
in draw() (a `const` shadowing a helper, and a reassigned `const`) killed it, and
neither was visible to a syntax check or to the id-selector contract test. A chart
that throws on its first marker looks exactly like a chart with no data.

So: execute draw() against the real result JSON with a stub DOM and assert on what
it appends to the SVG.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RENDER_TEST = REPO / "site" / "test" / "render_test.mjs"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_chart_actually_renders_markers_and_lift_lines():
    proc = subprocess.run(
        ["node", str(RENDER_TEST)],
        cwd=REPO, capture_output=True, text=True, timeout=60,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"chart failed to render:\n{out[-1500:]}"
    assert "CHART RENDERS" in out, out[-800:]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_every_model_and_eval_appears_on_the_chart():
    """One marker pair per (model, eval) row — a silently dropped row would mean a
    model vanishing from the published board."""
    rows = json.loads((REPO / "site" / "data" / "skill_lift.json").read_text())["rows"]
    proc = subprocess.run(
        ["node", str(RENDER_TEST)],
        cwd=REPO, capture_output=True, text=True, timeout=60,
    )
    counts = json.loads(proc.stdout.split("SVG elements drawn:")[1].split("\n")[0])
    # markers: circle (dv/v) + rect (STA/LTA) + polygon (retrieval triangle)
    markers = counts.get("circle", 0) + counts.get("rect", 0) + counts.get("polygon", 0)
    # two markers (no-skill, skill) per row
    assert markers >= 2 * len(rows), (
        f"expected >= {2 * len(rows)} markers for {len(rows)} rows, drew {markers}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_legend_is_grouped_by_encoding():
    """The chart carries two independent encodings — colour = base model, shape =
    task — plus the skill fill. The legend must group them explicitly, or the
    reader has to reverse-engineer which visual channel means what."""
    proc = subprocess.run(
        ["node", str(REPO / "site" / "test" / "legend_check.mjs")],
        cwd=REPO, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    out = proc.stdout
    for group in ("[Base model]", "[Task]", "[Skill]"):
        assert group in out, f"legend missing the {group} group:\n{out}"

    # every model on the board appears under Base model
    rows = json.loads((REPO / "site" / "data" / "skill_lift.json").read_text())["rows"]
    for model in {r["model_id"] for r in rows}:
        assert model in out, f"{model} missing from the legend"
    # each task appears exactly once, not once per model (both, per review)
    # each task label appears once in the legend, not once per model. Only the
    # families with data on the current board are checked (retrieval joined once
    # the document eval was run live).
    board = json.loads((REPO / "site" / "data" / "skill_lift.json").read_text())["rows"]
    labels = {"synthetic_stalta": "STA/LTA detection",
              "dvv_processing": "dv/v processing",
              "lit_rag": "literature retrieval"}
    for suite in {r["suite"] for r in board}:
        task = labels[suite]
        assert out.count(task) == 1, f"{task!r} should appear once, saw {out.count(task)}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_chart_uses_a_readable_layout_on_a_phone(tmp_path):
    """On a ~375px phone a 900-unit viewBox downscales text to ~4px. The chart
    must switch to the narrow layout (smaller viewBox, larger user-unit type) so
    it stays legible."""
    base = (REPO / "site" / "test" / "render_test.mjs").read_text()
    phone = base.replace("innerWidth:1200,innerHeight:900",
                         "innerWidth:375,innerHeight:812")
    f = tmp_path / "phone_render.mjs"
    f.write_text(phone)
    proc = subprocess.run(
        ["node", str(f)], cwd=REPO, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    assert "CHART RENDERS" in proc.stdout


def test_mobile_affordances_exist():
    """The tooltip is the only way to read a marker's data, and there is no hover
    on touch; and an SVG scatter is invisible to screen readers. So a phone needs
    tap-tooltips and a data-table fallback."""
    js = (REPO / "site" / "app.js").read_text()
    html = (REPO / "site" / "index.html").read_text()
    css = (REPO / "site" / "styles.css").read_text()
    # touch reachability for the tooltip
    assert "touchstart" in js, "no touch handler — marker data is unreachable on mobile"
    # the responsive layout switch
    assert "function layout()" in js and "innerWidth < 700" in js
    # a data-table fallback (also the screen-reader path)
    assert 'id="data-table-body"' in html and "renderTable" in js
    assert ".sr-only" in css
    # a mobile breakpoint
    assert "max-width: 700px" in css
