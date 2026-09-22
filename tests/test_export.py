"""Tests for the standard suite exporter (repere.export)."""

from __future__ import annotations

import hashlib
import json

import pytest

from repere.export import BenchmarkRow, export_suite, export_suites
from repere_suites.sta_lta import (
    ALL_SUITES,
    STALTAFetchCodeSuite,
    STALTAIntentExtractionSuite,
    STALTAPlotSuite,
    STALTAReportSuite,
    STALTATriggerCodeSuite,
)

REQUIRED_FIELDS = {
    "id",
    "dataset_id",
    "suite_id",
    "version",
    "task_kind",
    "split",
    "visibility",
    "prompt",
    "gold",
    "scorer_spec",
    "metadata",
}


@pytest.fixture
def all_suites():
    return [
        STALTAIntentExtractionSuite(),
        STALTAFetchCodeSuite(),
        STALTATriggerCodeSuite(),
        STALTAPlotSuite(),
        STALTAReportSuite(),
    ]


def test_every_suite_declares_identity(all_suites):
    for suite in all_suites:
        assert suite.dataset_id, f"{type(suite).__name__} missing dataset_id"
        assert suite.suite_id, f"{type(suite).__name__} missing suite_id"
        assert suite.version, f"{type(suite).__name__} missing version"


def test_export_rows_yields_benchmark_rows(all_suites):
    for suite in all_suites:
        rows = list(suite.export_rows())
        assert rows, f"{type(suite).__name__} returned 0 export rows"
        for row in rows:
            assert isinstance(row, BenchmarkRow)
            assert set(row.__dict__.keys()) >= REQUIRED_FIELDS - {"metadata"}
            assert row.dataset_id == suite.dataset_id
            assert row.suite_id == suite.suite_id
            assert row.id.startswith(f"{suite.dataset_id}/{suite.suite_id}/")
            assert row.split in {"validation", "test"}
            assert row.visibility in {"public", "private"}
            assert isinstance(row.scorer_spec, dict) and "name" in row.scorer_spec


def test_items_and_export_rows_are_in_sync(all_suites):
    """Same prompt+gold from items() and export_rows() — guards against drift."""
    for suite in all_suites:
        from_items = [(p, g) for p, g, _ in suite.items()]
        from_export = [(r.prompt, r.gold) for r in suite.export_rows()]
        assert from_items == from_export, f"items()/export_rows() drift in {type(suite).__name__}"


def test_export_suite_writes_jsonl(tmp_path):
    suite = STALTAIntentExtractionSuite()
    out = export_suite(suite, out_dir=tmp_path)
    assert out.exists()
    assert out.suffix == ".jsonl"
    assert out.parent.name == suite.version
    assert out.parent.parent.name == suite.dataset_id

    lines = out.read_text().splitlines()
    rows = [json.loads(line) for line in lines]
    assert len(rows) >= 1
    for row in rows:
        assert REQUIRED_FIELDS <= set(row)
        assert row["dataset_id"] == "sta_lta"
        assert row["suite_id"] == "intent_extraction"


def test_export_suites_writes_manifest_with_hashes(tmp_path, all_suites):
    manifest = export_suites(all_suites, out_dir=tmp_path)
    assert manifest["files"], "manifest empty"
    assert len(manifest["files"]) == len(all_suites)

    # On-disk manifest exists per dataset/version
    on_disk = tmp_path / "sta_lta" / "v0.1" / "manifest.json"
    assert on_disk.exists()
    parsed = json.loads(on_disk.read_text())
    assert parsed["dataset_id"] == "sta_lta"
    assert parsed["version"] == "v0.1"
    assert {entry["suite_id"] for entry in parsed["files"]} == {
        "intent_extraction",
        "fetch_code",
        "trigger_code",
        "plot",
        "report",
    }

    # sha256 in manifest matches actual file hash
    for entry in parsed["files"]:
        path = tmp_path / entry["path"]
        assert path.exists()
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert entry["sha256"] == actual
        assert entry["rows"] >= 1


def test_visibility_filter_via_attr(tmp_path):
    """When a suite is constructed with visibility='public', private events drop."""
    suite_all = STALTAIntentExtractionSuite()
    suite_pub = STALTAIntentExtractionSuite(visibility="public")
    n_all = len(list(suite_all.export_rows()))
    n_pub = len(list(suite_pub.export_rows()))
    assert 0 < n_pub <= n_all
    for row in suite_pub.export_rows():
        assert row.visibility == "public"


def test_all_suites_constant_is_complete():
    """ALL_SUITES is what the CLI walks; keep it in sync with the class set."""
    ids = {f"{s.dataset_id}.{s.suite_id}" for s in ALL_SUITES}
    assert ids == {
        "sta_lta.intent_extraction",
        "sta_lta.fetch_code",
        "sta_lta.trigger_code",
        "sta_lta.plot",
        "sta_lta.report",
    }
