"""Negative tests for `_load_events` field validation.

Loader-time validation should fail loudly with an event id and a missing key
name when events.yaml is malformed, rather than letting a `KeyError` surface
deep inside `STALTAxxxSuite.items()` at run time.

These tests construct deliberately broken YAML in tmp paths and assert that
the loader raises `ValueError` with a helpful message.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from repere_suites.sta_lta.items import _load_events


# A complete, well-formed event used as a base; tests delete or mutate fields
# to construct negative cases.
GOOD_EVENT = {
    "id": "test-event",
    "category": "regional_earthquake",
    "label": "Test event",
    "origin_time": "2024-06-15T12:00:00",
    "expected_detection": True,
    "split": "validation",
    "visibility": "public",
    "cutoff_date": "2024-06-22",
    "recommended_stations": [
        {"network": "UW", "station": "X", "location": "", "channel": "BHZ"},
    ],
    "suggested_window_min": 10,
    "stalta_params": {"sta": 2.0, "lta": 10.0, "on_thresh": 3.5, "off_thresh": 1.5},
}


def _write(events: list[dict], tmp_path: Path) -> Path:
    p = tmp_path / "events.yaml"
    p.write_text(yaml.safe_dump({"schema_version": 0.3, "events": events}))
    return p


def _without(field: str) -> dict:
    ev = dict(GOOD_EVENT)
    ev.pop(field)
    return ev


# ---- Top-level required fields ------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "category",
        "label",
        "origin_time",
        "expected_detection",
        "recommended_stations",
        "suggested_window_min",
        "stalta_params",
        "split",
        "visibility",
    ],
)
def test_loader_rejects_missing_top_level_field(tmp_path, field):
    p = _write([_without(field)], tmp_path)
    with pytest.raises(ValueError, match=field):
        _load_events(p)


# ---- stalta_params nested validation ------------------------------------


def test_loader_rejects_non_mapping_stalta_params(tmp_path):
    ev = dict(GOOD_EVENT)
    ev["stalta_params"] = [1.0, 2.0, 3.0]
    p = _write([ev], tmp_path)
    with pytest.raises(ValueError, match="stalta_params must be a mapping"):
        _load_events(p)


@pytest.mark.parametrize("missing", ["sta", "lta", "on_thresh", "off_thresh"])
def test_loader_rejects_missing_stalta_param(tmp_path, missing):
    ev = dict(GOOD_EVENT)
    ev["stalta_params"] = {k: v for k, v in GOOD_EVENT["stalta_params"].items() if k != missing}
    p = _write([ev], tmp_path)
    with pytest.raises(ValueError, match=f"stalta_params missing required key {missing!r}"):
        _load_events(p)


# ---- recommended_stations nested validation -----------------------------


def test_loader_rejects_empty_recommended_stations(tmp_path):
    ev = dict(GOOD_EVENT)
    ev["recommended_stations"] = []
    p = _write([ev], tmp_path)
    with pytest.raises(ValueError, match="recommended_stations must be a non-empty list"):
        _load_events(p)


def test_loader_rejects_non_mapping_station_entry(tmp_path):
    ev = dict(GOOD_EVENT)
    ev["recommended_stations"] = ["UW.X..BHZ"]  # bare string instead of a dict
    p = _write([ev], tmp_path)
    with pytest.raises(ValueError, match="recommended_stations\\[0\\] must be a mapping"):
        _load_events(p)


@pytest.mark.parametrize("missing", ["network", "station", "location", "channel"])
def test_loader_rejects_station_missing_field(tmp_path, missing):
    ev = dict(GOOD_EVENT)
    bad_station = {k: v for k, v in GOOD_EVENT["recommended_stations"][0].items() if k != missing}
    ev["recommended_stations"] = [bad_station]
    p = _write([ev], tmp_path)
    with pytest.raises(ValueError, match=f"recommended_stations\\[0\\] missing key {missing!r}"):
        _load_events(p)


# ---- Error messages mention the offending event id ----------------------


def test_error_message_includes_event_id(tmp_path):
    """Validation error must surface the event id so debugging is fast."""
    ev = dict(GOOD_EVENT, id="my-broken-event")
    ev.pop("label")
    p = _write([ev], tmp_path)
    with pytest.raises(ValueError, match="my-broken-event"):
        _load_events(p)


# ---- Top-level shape: events list and each entry must be a mapping ------


def test_loader_rejects_non_list_events_field(tmp_path):
    p = tmp_path / "events.yaml"
    p.write_text(yaml.safe_dump({"schema_version": 0.3, "events": "not-a-list"}))
    with pytest.raises(ValueError, match="`events` must be a list"):
        _load_events(p)


@pytest.mark.parametrize(
    "bad_entry, label",
    [
        ("just-a-string", "string"),
        (["network", "UW"], "list"),
        (42, "scalar"),
        (None, "null"),
    ],
)
def test_loader_rejects_non_mapping_event_entry(tmp_path, bad_entry, label):
    """A stray non-mapping entry must raise ValueError with the index, not AttributeError."""
    p = _write([dict(GOOD_EVENT), bad_entry], tmp_path)
    with pytest.raises(ValueError, match=r"events\[1\] must be a mapping"):
        _load_events(p)


def test_non_mapping_entry_error_includes_index(tmp_path):
    p = _write(["bare-string", dict(GOOD_EVENT)], tmp_path)
    # Index 0 is the offender; the message must say so.
    with pytest.raises(ValueError, match=r"events\[0\] must be a mapping"):
        _load_events(p)


# ---- Sanity: the GOOD_EVENT itself loads cleanly ------------------------


def test_good_event_loads_without_error(tmp_path):
    p = _write([dict(GOOD_EVENT)], tmp_path)
    [ev] = _load_events(p)
    assert ev["id"] == "test-event"
