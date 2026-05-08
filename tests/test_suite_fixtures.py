"""Drift detector for the four parametric STA/LTA suites.

The fixtures under `tests/fixtures/` are static dumps of `{prompt, gold}`
produced by `scripts/build_suite_fixtures.py`. If `events.yaml` or the suite
prompt templates change, this test fails — and the right fix is to either
revert the change or regenerate the fixtures and review the diff.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frugalmind_suites.sta_lta import (
    STALTAFetchCodeSuite,
    STALTAIntentExtractionSuite,
    STALTAReportSuite,
    STALTATriggerCodeSuite,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def _coerce_for_compare(gold):
    """Normalise gold values the same way the dumper does."""
    try:
        json.dumps(gold)
        return gold
    except TypeError:
        return repr(gold)


def _load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / f"{name}.json"
    return json.loads(path.read_text())


@pytest.mark.parametrize(
    "suite_id,suite",
    [
        ("sta_lta.intent_extraction", STALTAIntentExtractionSuite()),
        ("sta_lta.fetch_code", STALTAFetchCodeSuite()),
        ("sta_lta.trigger_code", STALTATriggerCodeSuite()),
        ("sta_lta.report", STALTAReportSuite()),
    ],
)
def test_live_suite_matches_committed_fixture(suite_id, suite):
    fixture = _load_fixture(suite_id)
    live_items = list(suite.items())
    assert len(live_items) == fixture["n_items"], (
        f"{suite_id}: live suite has {len(live_items)} items but fixture has "
        f"{fixture['n_items']}; regenerate fixtures with "
        f"`python scripts/build_suite_fixtures.py`"
    )
    for live, fixed in zip(live_items, fixture["items"]):
        prompt, gold, _scorer = live
        assert prompt == fixed["prompt"], (
            f"{suite_id} item {fixed['item_index']}: prompt drift detected. "
            "Regenerate fixtures or revert prompt template change."
        )
        assert _coerce_for_compare(gold) == fixed["gold"], (
            f"{suite_id} item {fixed['item_index']}: gold drift detected. "
            "Regenerate fixtures or revert gold construction change."
        )


def test_all_four_fixtures_are_committed():
    expected = {
        "sta_lta.intent_extraction.json",
        "sta_lta.fetch_code.json",
        "sta_lta.trigger_code.json",
        "sta_lta.report.json",
    }
    have = {p.name for p in FIXTURES_DIR.glob("*.json")}
    missing = expected - have
    assert not missing, f"missing fixtures: {sorted(missing)}"
