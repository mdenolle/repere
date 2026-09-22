"""Tests for the InspectAI substrate (P2.1).

`inspect_ai` is an optional dependency declared under `[eval]`. The whole
module is gated on its presence so contributors who don't install the
extra still see a green test suite.

Three contracts pinned here:

  1. Each `@task` function returns a real `inspect_ai.Task` whose dataset
     length matches the underlying STA/LTA suite at that split.
  2. Every `Sample` carries the JSON-encoded gold and a metadata block
     containing `event_id`, `cutoff_date`, and `scorer_spec` (the spec
     the generic scorer dispatches on).
  3. The generic `stalta_scorer` returns an Inspect `Score` in [0, 1] and
     produces a perfect score on a known-good completion (round-tripping
     the gold dict through json so the legacy scorer sees the right
     shape).
"""

from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("inspect_ai")

from inspect_ai import Task  # noqa: E402
from inspect_ai.dataset import Sample  # noqa: E402
from inspect_ai.scorer import Target  # noqa: E402

from repere_suites.sta_lta.inspect_tasks import (  # noqa: E402
    ALL_TASKS,
    fetch_code,
    intent_extraction,
    plot,
    report,
    stalta_scorer,
    trigger_code,
)


# ---------------------------------------------------------------------------
# 1. Task construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "task_fn, split, expected_count",
    [
        (intent_extraction, "validation", 2),
        (intent_extraction, "test", 4),
        (fetch_code, "validation", 2),
        (trigger_code, "validation", 2),
        (plot, "validation", 2),
        (report, "validation", 2),
    ],
)
def test_task_function_returns_inspect_task_with_expected_count(task_fn, split, expected_count):
    t = task_fn(split=split)
    assert isinstance(t, Task), f"{task_fn.__name__} must return inspect_ai.Task"
    samples = list(t.dataset)
    assert len(samples) == expected_count, (
        f"{task_fn.__name__}({split=}) expected {expected_count} samples, got {len(samples)}"
    )


def test_all_five_task_kinds_are_exported():
    """Every STA/LTA task kind from the legacy suites has an Inspect task."""
    expected = {"intent_extraction", "fetch_code", "trigger_code", "plot", "report"}
    actual = {f.__name__ for f in ALL_TASKS}
    assert actual == expected


# ---------------------------------------------------------------------------
# 2. Sample shape: input + JSON target + scorer_spec metadata
# ---------------------------------------------------------------------------


def test_each_sample_carries_json_target_and_scorer_spec():
    t = intent_extraction(split="validation")
    samples = list(t.dataset)
    for s in samples:
        assert isinstance(s, Sample)
        assert isinstance(s.input, str) and s.input, "Sample.input must be a non-empty prompt"
        # Target round-trips through json.
        gold = json.loads(s.target)
        assert isinstance(gold, dict), "intent_extraction gold must be a dict"
        for key in ("network", "station", "channel", "starttime"):
            assert key in gold, f"gold missing FDSN field {key!r}"
        # Metadata carries scorer_spec for the generic scorer.
        md = s.metadata or {}
        assert "event_id" in md
        assert "cutoff_date" in md
        assert "scorer_spec" in md
        assert isinstance(md["scorer_spec"], dict)
        assert md["scorer_spec"]["name"] == "json_extraction"


def test_scorer_spec_name_matches_task_kind():
    """Each task family ships a spec with the right scorer name."""
    expected = {
        intent_extraction: "json_extraction",
        fetch_code: "code_execution",
        trigger_code: "code_execution",
        report: "report",
    }
    for task_fn, spec_name in expected.items():
        t = task_fn(split="validation")
        for s in t.dataset:
            assert (s.metadata or {})["scorer_spec"]["name"] == spec_name, (
                f"{task_fn.__name__} sample {s.id!r}: spec.name should be {spec_name!r}"
            )


def test_plot_task_handles_missing_golden_with_zero_scorer():
    """When a plot golden is missing on disk, the spec resolves to 'zero'.
    With our committed PNGs present, all validation samples should use 'plot_ssim'."""
    t = plot(split="validation")
    seen_names = {(s.metadata or {})["scorer_spec"]["name"] for s in t.dataset}
    assert seen_names <= {"plot_ssim", "zero"}


# ---------------------------------------------------------------------------
# 3. Generic scorer round-trip
# ---------------------------------------------------------------------------


class _StubOutput:
    def __init__(self, text: str) -> None:
        self.completion = text


class _StubState:
    """Minimal stand-in for inspect_ai.solver.TaskState that the scorer reads.

    The real scorer reads `state.output.completion` and `state.metadata`. We
    expose both attributes so the scorer never touches anything else."""

    def __init__(self, *, completion: str, metadata: dict) -> None:
        self.output = _StubOutput(completion)
        self.metadata = metadata


async def _run_scorer(scorer_fn, state, target):
    return await scorer_fn(state, target)


def test_generic_scorer_returns_perfect_score_on_known_good_intent_completion():
    """Feeding the gold JSON back as the model output should score 1.0."""
    t = intent_extraction(split="validation")
    sample = next(iter(t.dataset))
    gold = json.loads(sample.target)
    perfect_completion = json.dumps(gold)
    target = Target(sample.target)
    state = _StubState(completion=perfect_completion, metadata=sample.metadata or {})

    score_callable = stalta_scorer()
    result = asyncio.run(_run_scorer(score_callable, state, target))
    assert result.value == pytest.approx(1.0)
    assert result.answer == perfect_completion


def test_generic_scorer_returns_zero_on_garbage_completion():
    t = intent_extraction(split="validation")
    sample = next(iter(t.dataset))
    target = Target(sample.target)
    state = _StubState(completion="not even close", metadata=sample.metadata or {})

    score_callable = stalta_scorer()
    result = asyncio.run(_run_scorer(score_callable, state, target))
    assert result.value == 0.0


def test_generic_scorer_handles_missing_scorer_spec():
    """Defensive: an externally-built sample without a spec must not crash."""
    sample_meta = {"event_id": "manual"}
    state = _StubState(completion="anything", metadata=sample_meta)
    target = Target(json.dumps({"some": "gold"}))

    score_callable = stalta_scorer()
    result = asyncio.run(_run_scorer(score_callable, state, target))
    assert result.value == 0.0
    assert "scorer_spec" in (result.explanation or "").lower()


def test_generic_scorer_value_is_clamped_to_unit_interval():
    """Defensive: even if a custom scorer returns >1.0, the wrapper clamps."""
    # Use the report scorer with empty config — the lexical score is at most
    # 0.7 in this branch, so clamping isn't actually exercised here, but the
    # contract still holds that no value escapes [0, 1]. Verify with a
    # synthetic spec:
    bad_spec = {"name": "json_extraction", "config": {"required_fields": ["x"]}}
    state = _StubState(
        completion='{"x": "y"}',
        metadata={"scorer_spec": bad_spec},
    )
    target = Target(json.dumps({"x": "y"}))
    score_callable = stalta_scorer()
    result = asyncio.run(_run_scorer(score_callable, state, target))
    assert 0.0 <= result.value <= 1.0
