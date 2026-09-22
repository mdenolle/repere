"""Drift detector for the four parametric STA/LTA suites.

The fixtures under `tests/fixtures/` are static dumps of `{prompt, gold}`
produced by `scripts/build_suite_fixtures.py`, one JSON per suite. If
`events.yaml` or any suite prompt template changes, this test fails — and the
right fix is to either revert the change or regenerate the fixtures and review
the diff.

Only the validation split is committed. A test-split fixture carries the
held-out gold (the reference stalta_params are spelled out in the prompt
text), so it lives in REPERE_EVAL_DATA_DIR with the held-out events. When that
partition is present locally these tests cover it too; when it is absent they
skip, which is what CI and a fresh clone see.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repere_suites.sta_lta import (
    STALTAFetchCodeSuite,
    STALTAIntentExtractionSuite,
    STALTAReportSuite,
    STALTATriggerCodeSuite,
)
from repere_suites.sta_lta.items import VALID_SPLITS


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"

SUITE_FACTORIES = {
    "sta_lta.intent_extraction": STALTAIntentExtractionSuite,
    "sta_lta.fetch_code": STALTAFetchCodeSuite,
    "sta_lta.trigger_code": STALTATriggerCodeSuite,
    "sta_lta.report": STALTAReportSuite,
}

PUBLIC_SPLIT = "validation"
EXPECTED_SPLIT_SIZES = {"validation": 2, "test": 4}


def _coerce_for_compare(gold):
    """Normalise gold values the same way the dumper does."""
    try:
        json.dumps(gold)
        return gold
    except TypeError:
        return repr(gold)


def _load_fixture(suite_id: str, split: str) -> dict:
    from repere_suites.sta_lta.items import PRIVATE_DIR

    # Held-out fixtures live with the held-out events, never in the repo.
    base = (PRIVATE_DIR / "fixtures") if split == "test" else FIXTURES_DIR
    path = base / f"{suite_id}.{split}.json"
    return json.loads(path.read_text())


@pytest.mark.parametrize(
    "suite_id,split",
    [(sid, split) for sid in SUITE_FACTORIES for split in VALID_SPLITS],
)
def test_live_suite_matches_committed_fixture(suite_id, split):
    """The live suite at this split must match the per-(suite, split) fixture."""
    from repere_suites.sta_lta.items import HIDDEN_EVENTS_PATH, _load_events

    if split == "test" and not HIDDEN_EVENTS_PATH.is_file():
        pytest.skip(f"held-out partition absent ({HIDDEN_EVENTS_PATH})")

    suite = SUITE_FACTORIES[suite_id](split=split)
    fixture = _load_fixture(suite_id, split)
    assert fixture["split"] == split, (
        f"{suite_id}.{split}.json: 'split' field mismatch "
        f"(expected {split!r}, got {fixture['split']!r})"
    )
    live_items = list(suite.items())
    live_events = _load_events(split=split)
    assert len(live_items) == fixture["n_items"], (
        f"{suite_id} (split={split}): live suite has {len(live_items)} items "
        f"but fixture has {fixture['n_items']}; regenerate with "
        f"`python scripts/build_suite_fixtures.py`"
    )
    for ev, live, fixed in zip(live_events, live_items, fixture["items"]):
        prompt, gold, _scorer = live
        assert prompt == fixed["prompt"], (
            f"{suite_id} (split={split}) item {fixed['item_index']}: "
            "prompt drift detected. Regenerate fixtures or revert prompt change."
        )
        assert _coerce_for_compare(gold) == fixed["gold"], (
            f"{suite_id} (split={split}) item {fixed['item_index']}: "
            "gold drift detected. Regenerate fixtures or revert gold change."
        )
        # Metadata pass-through: every fixture item must carry event_id and cutoff_date,
        # and they must match the live event.
        meta = fixed.get("metadata")
        assert meta is not None, (
            f"{suite_id} (split={split}) item {fixed['item_index']}: missing metadata block"
        )
        assert meta["event_id"] == ev["id"]
        assert meta["cutoff_date"] == ev["cutoff_date"]


@pytest.mark.parametrize("split,expected", EXPECTED_SPLIT_SIZES.items())
def test_each_split_has_expected_event_count(split, expected):
    from repere_suites.sta_lta.items import HIDDEN_EVENTS_PATH

    if split == "test" and not HIDDEN_EVENTS_PATH.is_file():
        pytest.skip(f"held-out partition absent ({HIDDEN_EVENTS_PATH})")
    suite = STALTAIntentExtractionSuite(split=split)
    items = list(suite.items())
    assert len(items) == expected, f"split={split} should have {expected} items; got {len(items)}"


def test_the_four_validation_fixtures_are_committed():
    expected = {f"{sid}.{PUBLIC_SPLIT}.json" for sid in SUITE_FACTORIES}
    have = {p.name for p in FIXTURES_DIR.glob("*.json")}
    missing = expected - have
    extra = have - expected
    assert not missing, f"missing fixtures: {sorted(missing)}"
    assert not extra, (
        f"unexpected fixtures: {sorted(extra)}; regenerate with "
        "`python scripts/build_suite_fixtures.py` and delete the leftovers."
    )


def test_no_holdout_fixture_is_committed():
    """A committed *.test.json would publish the held-out prompts and gold."""
    leaked = sorted(p.name for p in FIXTURES_DIR.glob("*.test.json"))
    assert not leaked, (
        f"held-out fixtures committed under tests/fixtures/: {leaked}. "
        "They carry the test-split gold (the reference stalta_params are "
        "spelled out in the prompt text). Move them to "
        "$REPERE_EVAL_DATA_DIR/fixtures/ and regenerate with "
        "`python scripts/build_suite_fixtures.py`, which writes only "
        "validation fixtures into the repo."
    )
