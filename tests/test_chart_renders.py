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
    markers = counts.get("circle", 0) + counts.get("rect", 0)
    # two markers (no-skill, skill) per row
    assert markers >= 2 * len(rows), (
        f"expected >= {2 * len(rows)} markers for {len(rows)} rows, drew {markers}"
    )
