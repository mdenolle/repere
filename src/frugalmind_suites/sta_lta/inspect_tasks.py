"""InspectAI substrate for the STA/LTA suites (P2.1).

Exposes one ``@task`` function per task kind so an external runner can do::

    inspect eval frugalmind/sta_lta_intent_extraction \
        --solver generate --model openai/gpt-4o-mini --limit 1

The InspectAI integration coexists with the legacy ``EvalRunner`` /
``LeaderboardRunner`` — neither path was modified. Each Inspect ``Task``
reuses ``_compose`` from :mod:`frugalmind_suites.sta_lta.items` so the
prompts, golds, and scorer specs match what the legacy runners emit
exactly. Drift would be caught by ``tests/test_inspect_tasks.py``.

Why a single generic scorer? The serialisable scorer spec each event
carries (``{"name": ..., "config": {...}}``) is enough to reconstruct
the existing ``make_*_scorer`` callables via
:func:`make_scorer_from_spec`. The scorer reads the spec from the
sample's metadata, calls the legacy scorer, and wraps the float in an
Inspect ``Score``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

# `inspect_ai` is an optional dependency declared under the [eval] extra.
# Importing this module without inspect_ai installed raises ImportError;
# tests gate on the presence of the import.
from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import Score, Target, accuracy, mean, scorer
from inspect_ai.solver import TaskState, generate

from .items import (
    STALTAFetchCodeSuite,
    STALTAIntentExtractionSuite,
    STALTAPlotSuite,
    STALTAReportSuite,
    STALTATriggerCodeSuite,
    _SplitAwareSuite,
)
from .scorers import make_scorer_from_spec


__all__ = [
    "fetch_code",
    "intent_extraction",
    "plot",
    "report",
    "stalta_scorer",
    "trigger_code",
]


def _samples_from_suite(suite: _SplitAwareSuite) -> MemoryDataset:
    """Materialise an Inspect dataset from one of the STA/LTA suites.

    Each event becomes one ``Sample``:

    * ``input``     — the suite's prompt (string).
    * ``target``    — the gold dict, JSON-encoded so the scorer can
                       round-trip it back to a Python object.
    * ``metadata``  — event_id, category, cutoff_date, expected_detection,
                       *plus* the JSON-serialisable scorer spec so the
                       generic scorer can dispatch.
    """
    samples: list[Sample] = []
    for ev in suite._events():
        prompt, gold, scorer_spec, meta = suite._compose(ev)
        # `default=str` covers e.g. datetime.date values from PyYAML's date parser.
        target_str = json.dumps(gold, sort_keys=True, default=str)
        sample_meta = {**meta, "scorer_spec": scorer_spec}
        samples.append(
            Sample(
                id=meta["event_id"],
                input=prompt,
                target=target_str,
                metadata=sample_meta,
            )
        )
    return MemoryDataset(samples=samples)


def _resolve_gold(target_text: str) -> Any:
    """Round-trip the JSON-encoded gold back to a Python object.

    Falls through to the raw string for cases where ``json.loads`` would
    raise (defensive — every suite encodes JSON, but a custom dataset
    written outside `_samples_from_suite` might not).
    """
    try:
        return json.loads(target_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return target_text


@scorer(metrics=[mean(), accuracy()])
def stalta_scorer():
    """Inspect scorer that dispatches via ``sample.metadata['scorer_spec']``.

    The legacy ``make_scorer_from_spec`` reconstructs the per-suite
    callable (json_extraction, code_execution, plot_ssim, report, zero).
    Returns an Inspect ``Score`` whose ``value`` is the legacy float in
    ``[0, 1]`` and whose ``answer`` is the model completion.
    """

    async def score(state: TaskState, target: Target) -> Score:
        completion = state.output.completion if state.output else ""
        gold = _resolve_gold(str(target.text))
        spec = (state.metadata or {}).get("scorer_spec") if hasattr(state, "metadata") else None
        if not spec:
            # Fall back to a sample-level lookup if the loader didn't merge.
            sample_md = getattr(state, "sample", None)
            if sample_md is not None:
                spec = (getattr(sample_md, "metadata", {}) or {}).get("scorer_spec")
        if not spec:
            return Score(
                value=0.0,
                answer=completion,
                explanation="scorer_spec missing from sample metadata",
            )
        try:
            scorer_fn = make_scorer_from_spec(spec)
            value = float(scorer_fn(completion, gold))
        except Exception as exc:  # pragma: no cover — defensive
            return Score(value=0.0, answer=completion, explanation=f"scorer error: {exc}")
        return Score(
            value=max(0.0, min(1.0, value)),
            answer=completion,
            explanation=spec.get("name", "stalta-scorer"),
        )

    return score


def _make_task(
    suite_cls: type[_SplitAwareSuite],
    *,
    split: str,
    visibility: str | None = None,
) -> Task:
    """Shared task constructor; suite_cls picks which kind to materialise."""
    suite = suite_cls(split=split, visibility=visibility) if visibility else suite_cls(split=split)
    return Task(
        dataset=_samples_from_suite(suite),
        solver=generate(),
        scorer=stalta_scorer(),
    )


# ---------------------------------------------------------------------------
# @task entrypoints — one per STA/LTA suite. The decorator wraps the function
# so InspectAI can register, list, and reload them; calling the function
# directly returns a Task object suitable for `inspect eval` or for
# programmatic invocation via `inspect_ai.eval(...)`.
# ---------------------------------------------------------------------------


@task
def intent_extraction(split: str = "validation") -> Task:
    """Natural-language request → structured FDSN query (JSON extraction)."""
    return _make_task(STALTAIntentExtractionSuite, split=split)


@task
def fetch_code(split: str = "validation") -> Task:
    """Structured request → ObsPy waveform-fetching code."""
    return _make_task(STALTAFetchCodeSuite, split=split)


@task
def trigger_code(split: str = "validation") -> Task:
    """Loaded ObsPy stream → STA/LTA trigger code."""
    return _make_task(STALTATriggerCodeSuite, split=split)


@task
def plot(split: str = "validation") -> Task:
    """Stream → matplotlib figure compared against a golden PNG via SSIM."""
    return _make_task(STALTAPlotSuite, split=split)


@task
def report(split: str = "validation") -> Task:
    """STA/LTA detection result → one-paragraph technical report."""
    return _make_task(STALTAReportSuite, split=split)


# Convenience for ``inspect eval frugalmind/sta_lta`` style discovery: a
# tuple of all five tasks. Test code uses this; users can ignore it.
ALL_TASKS: Iterable[Any] = (
    intent_extraction,
    fetch_code,
    trigger_code,
    plot,
    report,
)
