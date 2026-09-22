"""InspectAI substrate for the synthetic STA/LTA suite (P2.1 pattern).

    inspect eval src/repere_suites/synthetic_stalta/inspect_tasks.py \
        --solver generate --model anthropic/claude-sonnet-4-6
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

from .items import SyntheticSTALTASuite
from .scorers import make_scorer_from_spec

__all__ = ["ridgecrest_detection", "synthetic_stalta_scorer", "ALL_TASKS"]


def _samples_from_suite(suite: SyntheticSTALTASuite) -> MemoryDataset:
    samples: list[Sample] = []
    for c in suite._cases():
        prompt, gold, scorer_spec, meta = suite._compose(c)
        samples.append(
            Sample(
                id=meta["case_id"],
                input=prompt,
                target=json.dumps(gold),
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
def synthetic_stalta_scorer():
    """Dispatch via ``sample.metadata['scorer_spec']`` to detection_picks."""

    async def score(state: TaskState, target: Target) -> Score:
        completion = state.output.completion if state.output else ""
        gold = _resolve_gold(str(target.text))
        spec = (state.metadata or {}).get("scorer_spec") if hasattr(state, "metadata") else None
        if not spec:
            return Score(value=0.0, answer=completion, explanation="scorer_spec missing")
        try:
            scorer_fn = make_scorer_from_spec(spec)
            value = float(await asyncio.to_thread(scorer_fn, completion, gold))
        except Exception as exc:  # pragma: no cover — defensive
            return Score(value=0.0, answer=completion, explanation=f"scorer error: {exc}")
        return Score(value=max(0.0, min(1.0, value)), answer=completion,
                     explanation=spec.get("name", "detection_picks"))

    return score


@task
def ridgecrest_detection(split: str = "validation") -> Task:
    """Waveform + STA/LTA params -> reported onsets, scored by pick_f1."""
    return Task(
        dataset=_samples_from_suite(SyntheticSTALTASuite(split=split)),
        solver=generate(),
        scorer=synthetic_stalta_scorer(),
    )


ALL_TASKS: Iterable[Any] = (ridgecrest_detection,)
