"""Tests for the JSONLTelemetry sink — v2 schema + v1 read-compat (P2.5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frugalmind import Generation
from frugalmind.telemetry import (
    TELEMETRY_SCHEMA_VERSION,
    JSONLTelemetry,
    _normalise_v1_to_v2,
    read_jsonl,
)

# ---------------------------------------------------------------------------
# v2 write contract
# ---------------------------------------------------------------------------


def test_run_header_and_footer_written(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    with JSONLTelemetry(
        path,
        run_metadata={"suite": "stalta"},
        task="sta_lta.intent_extraction",
        solver="generate",
        model="m1",
    ) as tel:
        run_id = tel.run_id
    records = read_jsonl(path)
    assert records[0]["type"] == "run_start"
    assert records[0]["schema_version"] == TELEMETRY_SCHEMA_VERSION
    assert records[0]["metadata"] == {"suite": "stalta"}
    assert records[0]["run_id"] == run_id
    # Inspect-style run-level attribution surfaces on the header.
    assert records[0]["task"] == "sta_lta.intent_extraction"
    assert records[0]["solver"] == "generate"
    assert records[0]["model"] == "m1"
    assert records[0]["created"]
    assert records[-1]["type"] == "run_end"
    assert records[-1]["ok"] is True
    assert records[-1]["run_id"] == run_id
    assert records[-1]["completed"]


def test_run_header_and_footer_use_a_single_timestamp(tmp_path):
    """Header and footer must each emit one logical wall-clock read — if
    ``ts`` and ``created`` (or ``ts`` and ``completed``) drifted by 1s
    at a second-boundary, the record would be internally inconsistent.
    Caught by P2.5 review."""
    path = tmp_path / "telemetry.jsonl"
    with JSONLTelemetry(path, task="t", solver="generate", model="m1"):
        pass
    records = read_jsonl(path)
    header, footer = records[0], records[-1]
    assert header["ts"] == header["created"], (
        f"run_start ts and created should be captured once; got "
        f"ts={header['ts']!r} created={header['created']!r}"
    )
    assert footer["ts"] == footer["completed"], (
        f"run_end ts and completed should be captured once; got "
        f"ts={footer['ts']!r} completed={footer['completed']!r}"
    )


def test_run_header_omits_unset_attribution_fields(tmp_path):
    """When the caller doesn't pass task/solver/model, those fields must
    not appear on the header — null attribution would mislead readers."""
    path = tmp_path / "telemetry.jsonl"
    with JSONLTelemetry(path):
        pass
    header = read_jsonl(path)[0]
    assert header["type"] == "run_start"
    for missing in ("task", "task_args", "solver", "model"):
        assert missing not in header, f"unset {missing!r} should be omitted, not nulled"


def test_log_sample_writes_v2_shape(tmp_path):
    """The new ``log_sample`` API writes type=sample with output / epoch /
    id / run_id — the Inspect-aligned shape."""
    path = tmp_path / "telemetry.jsonl"
    gen = Generation(
        text="hi",
        prompt_tokens=4,
        output_tokens=2,
        latency_s=0.1,
        cost_usd=0.0001,
        model_id="m1",
    )
    with JSONLTelemetry(path, task="t", solver="generate", model="m1") as tel:
        tel.log_sample(
            gen,
            score=0.8,
            suite="stalta.intent",
            epoch=3,
            skill_name="stalta-detection",
            skill_mode="full",
        )
        run_id = tel.run_id
    samples = [r for r in read_jsonl(path) if r["type"] == "sample"]
    assert len(samples) == 1
    rec = samples[0]
    assert rec["schema_version"] == TELEMETRY_SCHEMA_VERSION
    assert rec["run_id"] == run_id
    assert rec["id"] == "stalta.intent:3"
    assert rec["epoch"] == 3
    assert rec["score"] == 0.8
    assert rec["suite"] == "stalta.intent"
    assert rec["skill_name"] == "stalta-detection"
    assert rec["skill_mode"] == "full"
    # The generation dict now lands under "output", not "generation".
    assert "generation" not in rec
    assert rec["output"]["model_id"] == "m1"
    assert rec["output"]["text"] == "hi"


def test_explicit_sample_id_overrides_synthesis(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    gen = Generation(text="x", prompt_tokens=1, output_tokens=1, latency_s=0, cost_usd=0, model_id="m1")
    with JSONLTelemetry(path) as tel:
        tel.log_sample(gen, sample_id="custom-key", suite="s", epoch=7)
    rec = [r for r in read_jsonl(path) if r["type"] == "sample"][0]
    assert rec["id"] == "custom-key"


def test_log_sample_synthesises_id_from_epoch_only_when_suite_missing(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    gen = Generation(text="x", prompt_tokens=1, output_tokens=1, latency_s=0, cost_usd=0, model_id="m1")
    with JSONLTelemetry(path) as tel:
        tel.log_sample(gen, epoch=5)
    rec = [r for r in read_jsonl(path) if r["type"] == "sample"][0]
    assert rec["id"] == "sample:5"


def test_log_sample_omits_id_when_nothing_known(tmp_path):
    """A caller that passes neither sample_id nor suite/epoch shouldn't
    get a fabricated id — the record is id-less but still well-formed."""
    path = tmp_path / "telemetry.jsonl"
    gen = Generation(text="x", prompt_tokens=1, output_tokens=1, latency_s=0, cost_usd=0, model_id="m1")
    with JSONLTelemetry(path) as tel:
        tel.log_sample(gen)
    rec = [r for r in read_jsonl(path) if r["type"] == "sample"][0]
    assert "id" not in rec


# ---------------------------------------------------------------------------
# log_generation legacy alias still works, writes v2 shape
# ---------------------------------------------------------------------------


def test_log_generation_alias_writes_v2_record(tmp_path):
    """``log_generation`` is kept as a thin alias on top of ``log_sample``
    so external callers (notebooks, downstream tooling) don't break on
    the v1 → v2 cutover. The on-disk record is in v2 shape (type=sample,
    output, epoch) — the alias only translates the parameter name."""
    path = tmp_path / "telemetry.jsonl"
    gen = Generation(text="hi", prompt_tokens=4, output_tokens=2, latency_s=0.1, cost_usd=0.0001, model_id="m1")
    with JSONLTelemetry(path) as tel:
        tel.log_generation(
            gen,
            score=0.8,
            suite="stalta.intent",
            item_index=3,
            skill_name="stalta-detection",
            skill_mode="full",
        )
    samples = [r for r in read_jsonl(path) if r["type"] == "sample"]
    assert len(samples) == 1, "alias must still write a sample record"
    rec = samples[0]
    assert rec["epoch"] == 3, "item_index translated to epoch"
    assert "item_index" not in rec
    assert rec["output"]["text"] == "hi"
    assert "generation" not in rec


# ---------------------------------------------------------------------------
# events and crash semantics
# ---------------------------------------------------------------------------


def test_log_event_records_payload(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    with JSONLTelemetry(path) as tel:
        tel.log_event("budget", {"model_id": "m1", "spent_usd": 0.05})
        run_id = tel.run_id
    payloads = [r for r in read_jsonl(path) if r["type"] == "budget"]
    assert payloads[0]["payload"] == {"model_id": "m1", "spent_usd": 0.05}
    assert payloads[0]["run_id"] == run_id


def test_run_end_marks_failure(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    try:
        with JSONLTelemetry(path):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    records = read_jsonl(path)
    assert records[-1]["type"] == "run_end"
    assert records[-1]["ok"] is False


def test_appends_across_runs(tmp_path):
    """Two consecutive `with` blocks produce two distinct run_id values
    and the records stay separable by run_id."""
    path = tmp_path / "telemetry.jsonl"
    with JSONLTelemetry(path) as tel:
        tel.log_event("phase", {"name": "first"})
        first_id = tel.run_id
    with JSONLTelemetry(path) as tel:
        tel.log_event("phase", {"name": "second"})
        second_id = tel.run_id
    assert first_id != second_id
    records = read_jsonl(path)
    types = [r["type"] for r in records]
    assert types.count("run_start") == 2
    assert types.count("run_end") == 2
    phases = [r["payload"]["name"] for r in records if r["type"] == "phase"]
    assert phases == ["first", "second"]
    # Each phase record carries its own run_id matching its enclosing run.
    phase_records = [r for r in records if r["type"] == "phase"]
    assert phase_records[0]["run_id"] == first_id
    assert phase_records[1]["run_id"] == second_id


def test_explicit_run_id_is_honoured(tmp_path):
    """Callers (tests, reproducibility tooling) can pin run_id explicitly."""
    path = tmp_path / "telemetry.jsonl"
    with JSONLTelemetry(path, run_id="frozen-run-id") as tel:
        assert tel.run_id == "frozen-run-id"
    assert read_jsonl(path)[0]["run_id"] == "frozen-run-id"


# ---------------------------------------------------------------------------
# v1 read-compat shim
# ---------------------------------------------------------------------------


_FIXTURE_DIR = Path(__file__).parent / "fixtures"
V1_FIXTURE = _FIXTURE_DIR / "telemetry_v1_sample.jsonl"


def test_normalise_v1_renames_generation_to_output_and_item_index_to_epoch():
    v1_record = {
        "type": "generation",
        "ts": "2026-05-08T00:00:00Z",
        "generation": {"model_id": "m1", "text": "hi"},
        "score": 0.7,
        "suite": "stalta.intent",
        "item_index": 0,
    }
    v2 = _normalise_v1_to_v2(v1_record)
    assert v2["schema_version"] == 1, "migrated records carry origin marker"
    assert v2["type"] == "sample"
    assert v2["output"] == {"model_id": "m1", "text": "hi"}
    assert "generation" not in v2
    assert v2["epoch"] == 0
    assert "item_index" not in v2
    assert v2["id"] == "stalta.intent:0"


def test_normalise_v1_falls_back_to_epoch_only_id_when_suite_missing():
    v1_record = {"type": "generation", "generation": {"text": "x"}, "item_index": 2}
    v2 = _normalise_v1_to_v2(v1_record)
    assert v2["id"] == "sample:2"
    assert v2["epoch"] == 2


def test_normalise_v1_does_not_synthesise_id_when_no_epoch():
    """Partial v1 logs (no item_index) should pass through id-less so
    callers can detect the missing field rather than silently get a
    fabricated key."""
    v1_record = {"type": "generation", "generation": {"text": "x"}}
    v2 = _normalise_v1_to_v2(v1_record)
    assert "id" not in v2


def test_normalise_v1_leaves_run_start_and_run_end_intact():
    """The shim only touches per-sample records — header / footer / event
    records pre-date run_id and are left alone except for the
    schema_version marker."""
    v1_start = {"type": "run_start", "ts": "2026-01-01T00:00:00Z", "metadata": {"suite": "x"}}
    v2 = _normalise_v1_to_v2(v1_start)
    assert v2["type"] == "run_start"
    assert v2["schema_version"] == 1
    assert v2["metadata"] == {"suite": "x"}
    assert "run_id" not in v2, "v1 logs don't carry run_id; we don't fabricate one"


@pytest.mark.skipif(not V1_FIXTURE.exists(), reason="v1 fixture not present")
def test_read_jsonl_normalises_frozen_v1_fixture():
    """End-to-end regression test against a committed v1 log fixture —
    if read_jsonl drifts away from the v1 shim, this test catches it
    loudly. The fixture mirrors the shape produced by FrugalMind 0.3.0."""
    records = read_jsonl(V1_FIXTURE)
    # The fixture has 1 run_start + 2 generation records + 1 run_end.
    assert [r["type"] for r in records] == [
        "run_start",
        "sample",
        "sample",
        "run_end",
    ]
    # All records get the v1-origin marker.
    assert all(r.get("schema_version") == 1 for r in records)
    # Generation records are renamed to sample shape.
    samples = [r for r in records if r["type"] == "sample"]
    assert samples[0]["output"] == {"text": "hello", "model_id": "m1"}
    assert samples[0]["epoch"] == 0
    assert samples[0]["id"] == "stalta.intent:0"
    assert samples[1]["epoch"] == 1
    assert samples[1]["id"] == "stalta.intent:1"


def test_read_jsonl_can_return_raw_records():
    """``normalise=False`` returns on-disk bytes for tools that need to
    detect schema drift or assert on the exact wire format."""
    # Build a minimal v1 file inline so the assertion isn't fixture-dependent.
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(json.dumps({"type": "generation", "generation": {"x": 1}, "item_index": 0}) + "\n")
        tmp = fh.name

    try:
        raw = read_jsonl(tmp, normalise=False)
        assert raw[0]["type"] == "generation"
        assert "generation" in raw[0]
        assert "schema_version" not in raw[0]
    finally:
        Path(tmp).unlink(missing_ok=True)
