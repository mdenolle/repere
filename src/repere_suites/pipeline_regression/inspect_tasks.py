"""InspectAI substrate for the pipeline-regression suite (P2.1 pattern).

    inspect eval src/repere_suites/pipeline_regression/inspect_tasks.py \
        --solver generate --model anthropic/claude-sonnet-4-6 --limit 1

Reuses ``_compose`` from :mod:`repere_suites.pipeline_regression.items`
so the prompts, golds, and scorer specs match the legacy runners exactly. A
single generic Inspect scorer reconstructs the ``numerical_regression``
callable from the sample's ``scorer_spec`` metadata — same design as the
STA/LTA ``stalta_scorer``.

Note: real runs need a per-suite sandbox image carrying the heavy pipeline
deps (seisbench/torch, noisepy). Each sample's metadata carries the
``sandbox_image`` the pipeline expects; wiring it into the Inspect sandbox
is a follow-up (see docs/numerical_regression_scorer.md).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import Any

# `inspect_ai` is an optional dependency declared under the [eval] extra.
from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import Score, Target, accuracy, mean, scorer
from inspect_ai.solver import TaskState, generate

from .items import PipelineRegressionSuite
from .scorers import make_scorer_from_spec

__all__ = ["pipeline_regression", "pipeline_regression_scorer", "ALL_TASKS"]


def _samples_from_suite(suite: PipelineRegressionSuite) -> MemoryDataset:
    samples: list[Sample] = []
    for p in suite._pipelines():
        prompt, gold, scorer_spec, meta = suite._compose(p)
        target_str = json.dumps(gold, sort_keys=True, default=str)
        samples.append(
            Sample(
                id=meta["pipeline_id"],
                input=prompt,
                target=target_str,
                metadata={**meta, "scorer_spec": scorer_spec},
            )
        )
    return MemoryDataset(samples=samples)


def _resolve_gold(target_text: str) -> Any:
    try:
        return json.loads(target_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return target_text


@scorer(metrics=[mean(), accuracy()])
def pipeline_regression_scorer():
    """Dispatch via ``sample.metadata['scorer_spec']`` to the numeric scorer."""

    async def score(state: TaskState, target: Target) -> Score:
        completion = state.output.completion if state.output else ""
        gold = _resolve_gold(str(target.text))
        spec = (state.metadata or {}).get("scorer_spec") if hasattr(state, "metadata") else None
        if not spec:
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
            # Runs a sandbox subprocess; offload so it can't block the loop.
            value = float(await asyncio.to_thread(scorer_fn, completion, gold))
        except Exception as exc:  # pragma: no cover — defensive
            return Score(value=0.0, answer=completion, explanation=f"scorer error: {exc}")
        return Score(
            value=max(0.0, min(1.0, value)),
            answer=completion,
            explanation=spec.get("config", {}).get("metric", "numerical_regression"),
        )

    return score


@task
def pipeline_regression(split: str = "validation") -> Task:
    """Prompt → pipeline run → numeric output, scored by regression."""
    suite = PipelineRegressionSuite(split=split)
    return Task(
        dataset=_samples_from_suite(suite),
        solver=generate(),
        scorer=pipeline_regression_scorer(),
    )


ALL_TASKS: Iterable[Any] = (pipeline_regression,)
