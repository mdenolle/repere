"""InspectAI substrate for the orchestration suite (Family 3, P2.1 pattern).

    inspect eval src/repere_suites/orchestration/inspect_tasks.py \
        --solver generate --model anthropic/claude-sonnet-4-6

Reuses ``_compose`` from :mod:`repere_suites.orchestration.items`; a generic
Inspect scorer reconstructs the ``trajectory_dag`` callable from
``sample.metadata['scorer_spec']``.

Note: the default ``generate()`` solver has the model *emit* a plan as JSON.
A real orchestrator run needs a subagents-as-tools solver (each
``available_agent`` exposed as a callable tool) so the DAG is captured from the
actual tool-call trace — the substrate change described in
docs/orchestration_scorer.md.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import Score, Target, accuracy, mean, scorer
from inspect_ai.solver import TaskState, generate

from .items import OrchestrationSuite
from .scorers import make_scorer_from_spec

__all__ = ["orchestration", "orchestration_scorer", "ALL_TASKS"]


def _samples_from_suite(suite: OrchestrationSuite) -> MemoryDataset:
    samples: list[Sample] = []
    for t in suite._tasks():
        prompt, gold, scorer_spec, meta = suite._compose(t)
        samples.append(
            Sample(
                id=meta["task_id"],
                input=prompt,
                target=json.dumps(gold, sort_keys=True, default=str),
                metadata={**meta, "scorer_spec": scorer_spec},
            )
        )
    return MemoryDataset(samples=samples)


@scorer(metrics=[mean(), accuracy()])
def orchestration_scorer():
    """Dispatch via ``sample.metadata['scorer_spec']`` to the trajectory scorer."""

    async def score(state: TaskState, target: Target) -> Score:
        completion = state.output.completion if state.output else ""
        spec = (state.metadata or {}).get("scorer_spec") if hasattr(state, "metadata") else None
        if not spec:
            return Score(
                value=0.0,
                answer=completion,
                explanation="scorer_spec missing from sample metadata",
            )
        try:
            scorer_fn = make_scorer_from_spec(spec)
            value = float(await asyncio.to_thread(scorer_fn, completion, None))
        except Exception as exc:  # pragma: no cover — defensive
            return Score(value=0.0, answer=completion, explanation=f"scorer error: {exc}")
        return Score(
            value=max(0.0, min(1.0, value)),
            answer=completion,
            explanation=spec.get("name", "orchestration-scorer"),
        )

    return score


@task
def orchestration(split: str = "validation") -> Task:
    """Goal → DAG of subagent calls, scored on node/edge F1 + frugality."""
    return Task(
        dataset=_samples_from_suite(OrchestrationSuite(split=split)),
        solver=generate(),
        scorer=orchestration_scorer(),
    )


ALL_TASKS: Iterable[Any] = (orchestration,)
