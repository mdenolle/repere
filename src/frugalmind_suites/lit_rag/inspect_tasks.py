"""InspectAI substrate for the lit_rag suites (Family 1, P2.1 pattern).

    inspect eval src/frugalmind_suites/lit_rag/inspect_tasks.py@retrieval \
        --solver generate --model anthropic/claude-sonnet-4-6

One ``@task`` per deterministic scorer, each reusing ``_compose`` from
:mod:`frugalmind_suites.lit_rag.items`. A single generic Inspect scorer
reconstructs the per-row callable from ``sample.metadata['scorer_spec']`` —
same design as ``stalta_scorer``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import Score, Target, accuracy, mean, scorer
from inspect_ai.solver import TaskState, generate

from .items import (
    LitRagGroundedQASuite,
    LitRagRetrievalSuite,
    LitRagTranslationSuite,
    _LitRagSuite,
)
from .scorers import make_scorer_from_spec

__all__ = [
    "retrieval",
    "translation",
    "grounded_qa",
    "lit_rag_scorer",
    "ALL_TASKS",
]


def _samples_from_suite(suite: _LitRagSuite) -> MemoryDataset:
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


def _resolve_gold(target_text: str) -> Any:
    try:
        return json.loads(target_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return target_text


@scorer(metrics=[mean(), accuracy()])
def lit_rag_scorer():
    """Dispatch via ``sample.metadata['scorer_spec']`` to the Family-1 scorer."""

    async def score(state: TaskState, target: Target) -> Score:
        completion = state.output.completion if state.output else ""
        gold = _resolve_gold(str(target.text))
        spec = (state.metadata or {}).get("scorer_spec") if hasattr(state, "metadata") else None
        if not spec:
            return Score(
                value=0.0,
                answer=completion,
                explanation="scorer_spec missing from sample metadata",
            )
        try:
            value = float(make_scorer_from_spec(spec)(completion, gold))
        except Exception as exc:  # pragma: no cover — defensive
            return Score(value=0.0, answer=completion, explanation=f"scorer error: {exc}")
        return Score(
            value=max(0.0, min(1.0, value)),
            answer=completion,
            explanation=spec.get("name", "lit-rag-scorer"),
        )

    return score


def _make_task(suite_cls: type[_LitRagSuite], *, split: str) -> Task:
    return Task(
        dataset=_samples_from_suite(suite_cls(split=split)),
        solver=generate(),
        scorer=lit_rag_scorer(),
    )


@task
def retrieval(split: str = "validation") -> Task:
    """RAG retrieval: rank documents against a gold relevant set."""
    return _make_task(LitRagRetrievalSuite, split=split)


@task
def translation(split: str = "validation") -> Task:
    """Translation with domain-term preservation."""
    return _make_task(LitRagTranslationSuite, split=split)


@task
def grounded_qa(split: str = "validation") -> Task:
    """Grounded QA: citation-supported answers, no fabricated sources."""
    return _make_task(LitRagGroundedQASuite, split=split)


ALL_TASKS: Iterable[Any] = (retrieval, translation, grounded_qa)
