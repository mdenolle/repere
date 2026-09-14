"""RCA end-to-end through Inspect with scripted solvers (needs the [eval] extra
and obspy for the known-good self-test snippet; both skip cleanly otherwise)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

inspect_ai = pytest.importorskip("inspect_ai")

from frugalmind_suites.rca import SEEDS_DIR  # noqa: E402
from frugalmind_suites.rca.inspect_tasks import public_view, rca  # noqa: E402
from frugalmind_suites.rca.solvers import do_nothing, scripted  # noqa: E402

QC = "rca-coding-qc-continuity-001"
SELFTEST = SEEDS_DIR / "coding" / "_selftest"


def _run(solver, epochs=1, log_dir: str | None = None):
    import tempfile

    from inspect_ai import eval as inspect_eval

    log_dir = log_dir or tempfile.mkdtemp(prefix="fm_rca_logs_")
    logs = inspect_eval(
        rca(ids=QC),
        model="mockllm/model",
        solver=solver,
        epochs=epochs,
        display="none",
        log_dir=log_dir,
    )
    assert logs[0].status == "success", logs[0].error
    return logs[0]


def test_public_view_strips_gold():
    from frugalmind_suites.rca import load_records

    rec = load_records(ids=[QC])[0]
    v = public_view(rec)
    assert "args" not in v["scoring"]["checker"]
    assert "_path" not in v
    assert v["prompt"] == rec["prompt"]


def test_task_builds_and_hides_expected_values():
    t = rca(ids=QC)
    sample = list(t.dataset)[0]
    assert sample.id == QC
    assert "expected" not in json.dumps(sample.metadata)


def test_do_nothing_scores_zero_not_void():
    log = _run(do_nothing())
    sc = log.samples[0].scores["rca_scorer"]
    assert sc.value == 0.0
    assert not (sc.metadata or {}).get("void")


@pytest.mark.skipif(
    pytest.importorskip("obspy", reason="obspy needed for the self-test snippet") is None,
    reason="obspy",
)
def test_known_good_scores_one_and_known_bad_scores_stages_only():
    good = _run(scripted(str(SELFTEST / "good")), epochs=2)
    vals = [s.scores["rca_scorer"].value for s in good.samples]
    assert vals == [1.0, 1.0], [s.scores["rca_scorer"].explanation for s in good.samples]
    bad = _run(scripted(str(SELFTEST / "bad")))
    sc = bad.samples[0].scores["rca_scorer"]
    assert sc.value == pytest.approx(0.3)
    assert sc.metadata["stages"] == {"code": 1.0, "runs": 1.0, "correct": 0.0}


def test_runner_writes_result_files(tmp_path: Path):
    pytest.importorskip("obspy")
    from frugalmind_suites.rca.run import main

    rc = main(
        [
            "--ids",
            QC,
            "--solver",
            f"scripted:{SELFTEST / 'good'}",
            "--model",
            "mockllm/model",
            "--epochs",
            "2",
            "--out",
            str(tmp_path),
        ]
    )
    assert rc == 0
    run_dir = next(tmp_path.iterdir())
    summary = json.loads((run_dir / "summary.json").read_text())
    rows = [json.loads(line) for line in (run_dir / "samples.jsonl").read_text().splitlines()]
    assert summary["schema"] == "rca.result.v0.1"
    assert summary["records"][QC]["n"] == 2 and summary["records"][QC]["mean"] == 1.0
    assert summary["suite_aggregate"]["any_model_unpinned"] is True, (
        "mockllm is not in the price map"
    )
    assert {"model_requested", "cost_usd", "wall_clock_s", "n_tool_calls", "trace"} <= set(rows[0])
    assert any("template" in w for w in summary["warnings"])
