"""Tests for the `cutoff_date` field and its default rule.

`cutoff_date` is the date past which a retrieval-augmented agent must not
query catalogs / papers / station status pages. The loader fills the field
in for events that omit it, using the rule:

    expected_detection: true   →  origin_time + 7 days
    expected_detection: false  →  origin_time - 1 day

Every committed event in events.yaml carries `cutoff_date` explicitly, but
the helper is the source of truth for any future event that doesn't.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from repere_suites.sta_lta.items import (
    DEFAULT_NEGATIVE_CUTOFF_DAYS,
    DEFAULT_POSITIVE_CUTOFF_DAYS,
    _load_events,
    default_cutoff_date,
)


# ---- Default-rule helper --------------------------------------------------


def test_default_rule_positive_case_adds_seven_days():
    ev = {"origin_time": "2001-02-28T18:54:32.8", "expected_detection": True}
    assert default_cutoff_date(ev) == "2001-03-07"


def test_default_rule_negative_case_subtracts_one_day():
    ev = {"origin_time": "2023-08-15T03:00:00.0", "expected_detection": False}
    assert default_cutoff_date(ev) == "2023-08-14"


def test_default_rule_offsets_match_constants():
    # Positive rule offset
    ev = {"origin_time": "2024-01-01T00:00:00", "expected_detection": True}
    assert default_cutoff_date(ev) == "2024-01-08"
    assert DEFAULT_POSITIVE_CUTOFF_DAYS == 7

    # Negative rule offset
    ev = {"origin_time": "2024-01-01T00:00:00", "expected_detection": False}
    assert default_cutoff_date(ev) == "2023-12-31"
    assert DEFAULT_NEGATIVE_CUTOFF_DAYS == -1


def test_default_rule_treats_missing_expected_detection_as_positive():
    ev = {"origin_time": "2024-06-15T12:00:00"}
    assert default_cutoff_date(ev) == "2024-06-22"


def test_default_rule_handles_isoformat_with_timezone():
    ev = {"origin_time": "2024-06-15T12:00:00+00:00", "expected_detection": True}
    assert default_cutoff_date(ev) == "2024-06-22"


def test_default_rule_requires_origin_time():
    with pytest.raises(ValueError):
        default_cutoff_date({"expected_detection": True})


# ---- Loader fill behaviour ------------------------------------------------


def test_loader_fills_cutoff_date_when_missing(tmp_path):
    """If an event omits cutoff_date, the loader fills it via the default rule."""
    yaml_path = tmp_path / "events.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 0.3,
                "events": [
                    {
                        "id": "synthetic-positive",
                        "category": "regional_earthquake",
                        "label": "synthetic positive",
                        "origin_time": "2024-06-15T12:00:00",
                        "expected_detection": True,
                        "split": "validation",
                        "visibility": "public",
                        "recommended_stations": [
                            {"network": "UW", "station": "X", "location": "", "channel": "BHZ"},
                        ],
                        "suggested_window_min": 10,
                        "stalta_params": {
                            "sta": 2.0,
                            "lta": 10.0,
                            "on_thresh": 3.5,
                            "off_thresh": 1.5,
                        },
                        # cutoff_date intentionally omitted.
                    },
                    {
                        "id": "synthetic-negative",
                        "category": "noise_day",
                        "label": "synthetic negative",
                        "origin_time": "2024-06-15T12:00:00",
                        "expected_detection": False,
                        "split": "test",
                        "visibility": "private",
                        "recommended_stations": [
                            {"network": "UW", "station": "X", "location": "", "channel": "BHZ"},
                        ],
                        "suggested_window_min": 10,
                        "stalta_params": {
                            "sta": 2.0,
                            "lta": 10.0,
                            "on_thresh": 3.5,
                            "off_thresh": 1.5,
                        },
                    },
                ],
            }
        )
    )
    events = _load_events(yaml_path)
    by_id = {ev["id"]: ev for ev in events}
    assert by_id["synthetic-positive"]["cutoff_date"] == "2024-06-22"
    assert by_id["synthetic-negative"]["cutoff_date"] == "2024-06-14"


def test_loader_normalises_explicit_cutoff_date_string(tmp_path):
    yaml_path = tmp_path / "events.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 0.3,
                "events": [
                    {
                        "id": "explicit-cutoff",
                        "category": "regional_earthquake",
                        "label": "explicit cutoff",
                        "origin_time": "2024-06-15T12:00:00",
                        "expected_detection": True,
                        "split": "validation",
                        "visibility": "public",
                        "cutoff_date": "2024-12-25",
                        "recommended_stations": [
                            {"network": "UW", "station": "X", "location": "", "channel": "BHZ"},
                        ],
                        "suggested_window_min": 10,
                        "stalta_params": {
                            "sta": 2.0,
                            "lta": 10.0,
                            "on_thresh": 3.5,
                            "off_thresh": 1.5,
                        },
                    },
                ],
            }
        )
    )
    [ev] = _load_events(yaml_path)
    assert ev["cutoff_date"] == "2024-12-25"  # explicit value wins over default


def test_loader_rejects_malformed_cutoff_date(tmp_path):
    yaml_path = tmp_path / "events.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 0.3,
                "events": [
                    {
                        "id": "bad-cutoff",
                        "category": "regional_earthquake",
                        "label": "bad cutoff",
                        "origin_time": "2024-06-15T12:00:00",
                        "expected_detection": True,
                        "split": "validation",
                        "visibility": "public",
                        "cutoff_date": "tomorrow",
                        "recommended_stations": [
                            {"network": "UW", "station": "X", "location": "", "channel": "BHZ"},
                        ],
                        "suggested_window_min": 10,
                        "stalta_params": {
                            "sta": 2.0,
                            "lta": 10.0,
                            "on_thresh": 3.5,
                            "off_thresh": 1.5,
                        },
                    },
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="cutoff_date"):
        _load_events(yaml_path)


# ---- Real events.yaml -----------------------------------------------------


def test_every_committed_event_has_cutoff_date():
    """All 6 events in the real events.yaml must carry cutoff_date and match the rule."""
    for ev in _load_events():
        assert ev["cutoff_date"], f"{ev['id']} missing cutoff_date"
        # Each explicit cutoff should match the default rule (since we wrote
        # them deliberately to align with it).
        assert ev["cutoff_date"] == default_cutoff_date(ev), (
            f"{ev['id']}: explicit cutoff_date {ev['cutoff_date']} disagrees "
            f"with default rule {default_cutoff_date(ev)}"
        )
