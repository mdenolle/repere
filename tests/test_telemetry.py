from __future__ import annotations

from frugalmind import Generation
from frugalmind.telemetry import JSONLTelemetry, read_jsonl


def test_run_header_and_footer_written(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    with JSONLTelemetry(path, run_metadata={"suite": "stalta"}):
        pass
    records = read_jsonl(path)
    assert records[0]["type"] == "run_start"
    assert records[0]["metadata"] == {"suite": "stalta"}
    assert records[-1]["type"] == "run_end"
    assert records[-1]["ok"] is True


def test_log_generation_persists_fields(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    gen = Generation(
        text="hi",
        prompt_tokens=4,
        output_tokens=2,
        latency_s=0.1,
        cost_usd=0.0001,
        model_id="m1",
    )
    with JSONLTelemetry(path) as tel:
        tel.log_generation(
            gen,
            score=0.8,
            suite="stalta.intent",
            item_index=3,
            skill_name="stalta-detection",
            skill_mode="full",
        )
    records = [r for r in read_jsonl(path) if r["type"] == "generation"]
    assert len(records) == 1
    rec = records[0]
    assert rec["score"] == 0.8
    assert rec["suite"] == "stalta.intent"
    assert rec["item_index"] == 3
    assert rec["skill_name"] == "stalta-detection"
    assert rec["skill_mode"] == "full"
    assert rec["generation"]["model_id"] == "m1"
    assert rec["generation"]["text"] == "hi"


def test_log_event_records_payload(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    with JSONLTelemetry(path) as tel:
        tel.log_event("budget", {"model_id": "m1", "spent_usd": 0.05})
    payloads = [r for r in read_jsonl(path) if r["type"] == "budget"]
    assert payloads[0]["payload"] == {"model_id": "m1", "spent_usd": 0.05}


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
    path = tmp_path / "telemetry.jsonl"
    with JSONLTelemetry(path) as tel:
        tel.log_event("phase", {"name": "first"})
    with JSONLTelemetry(path) as tel:
        tel.log_event("phase", {"name": "second"})
    records = read_jsonl(path)
    types = [r["type"] for r in records]
    assert types.count("run_start") == 2
    assert types.count("run_end") == 2
    phases = [r["payload"]["name"] for r in records if r["type"] == "phase"]
    assert phases == ["first", "second"]
