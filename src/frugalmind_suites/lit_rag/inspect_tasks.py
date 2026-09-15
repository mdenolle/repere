"""InspectAI substrate for the lit_rag suites (Family 1, P2.1 pattern).

    inspect eval src/frugalmind_suites/lit_rag/inspect_tasks.py@retrieval \
        --solver generate --model anthropic/claude-sonnet-4-6

    # repeat-run reliability: 5 epochs, mean ± stderr per task
    inspect eval src/frugalmind_suites/lit_rag/inspect_tasks.py@abstention \
        -T epochs=5 --model ollama/qwen2.5:7b

One ``@task`` per suite, each built from the suite's ``export_rows()`` so the
Inspect sample is byte-identical to the exported JSONL row. A single generic
Inspect scorer reconstructs the per-row callable from
``sample.metadata['scorer_spec']`` — same design as ``stalta_scorer`` — and
lifts the attribution breakdown (citation validity / precision / recall,
fabricated ids, fact coverage, abstained) into ``Score.metadata`` so a
blended score never hides a fabricated citation.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import Score, Target, mean, scorer, stderr
from inspect_ai.solver import TaskState, generate

from frugalmind import DenolleGroupSuite

from .items import (
    LitRagAbstentionSuite,
    LitRagGroundedQASuite,
    LitRagKnownItemSuite,
    LitRagRetrievalSuite,
    LitRagTranslationSuite,
)
from .scorers import is_abstention, make_scorer_from_spec

__all__ = [
    "retrieval",
    "abstention",
    "grounded_qa",
    "translation",
    "known_item",
    "lit_rag_scorer",
    "ALL_TASKS",
]


def samples_from_suite(suite: DenolleGroupSuite) -> MemoryDataset:
    samples: list[Sample] = []
    for row in suite.export_rows():
        samples.append(
            Sample(
                id=row.id.rsplit("/", 1)[-1],
                input=row.prompt,
                target=json.dumps(row.gold, sort_keys=True, default=str),
                metadata={**row.metadata, "scorer_spec": row.scorer_spec},
            )
        )
    return MemoryDataset(samples=samples)


def _resolve_gold(target_text: str) -> Any:
    try:
        return json.loads(target_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return target_text


@scorer(metrics=[mean(), stderr()])
def lit_rag_scorer():
    """Dispatch via ``sample.metadata['scorer_spec']`` to the Family-1 scorer.

    ``Score.metadata`` carries ``abstained`` for every sample and, for
    ``attribution`` specs, the full breakdown dict, so the dashboard can slice
    fabrication rate and citation recall independently of the scalar.
    """

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
            scorer_fn = make_scorer_from_spec(spec)
            value = float(await asyncio.to_thread(scorer_fn, completion, gold))
        except Exception as exc:  # pragma: no cover — defensive
            return Score(value=0.0, answer=completion, explanation=f"scorer error: {exc}")
        meta: dict[str, Any] = {"abstained": is_abstention(completion)}
        breakdown = getattr(scorer_fn, "breakdown", None)
        if callable(breakdown):
            meta["attribution"] = breakdown(completion, gold)
        return Score(
            value=max(0.0, min(1.0, value)),
            answer=completion,
            explanation=spec.get("name", "lit-rag-scorer"),
            metadata=meta,
        )

    return score


def _make_task(suite: DenolleGroupSuite, *, epochs: int) -> Task:
    return Task(
        dataset=samples_from_suite(suite),
        solver=generate(),
        scorer=lit_rag_scorer(),
        epochs=epochs,
    )


@task
def retrieval(split: str = "validation", epochs: int = 1) -> Task:
    """OOI-RCA known-item retrieval: rank a hard shortlist (MRR)."""
    return _make_task(LitRagRetrievalSuite(split=split), epochs=epochs)


@task
def abstention(split: str = "validation", epochs: int = 1) -> Task:
    """OOI-RCA abstention: decline unanswerable queries, answer matched controls."""
    return _make_task(LitRagAbstentionSuite(split=split), epochs=epochs)


@task
def grounded_qa(split: str = "validation", epochs: int = 1) -> Task:
    """OOI-RCA grounded QA: cite by DOI, facts verbatim, or decline."""
    return _make_task(LitRagGroundedQASuite(split=split), epochs=epochs)


@task
def translation(split: str = "validation", epochs: int = 1) -> Task:
    """OOI-RCA translation with identifier preservation."""
    return _make_task(LitRagTranslationSuite(split=split), epochs=epochs)


@task
def known_item(epochs: int = 1) -> Task:
    """arXiv physics.geo-ph known-item retrieval (MRR)."""
    return _make_task(LitRagKnownItemSuite(), epochs=epochs)


ALL_TASKS: Iterable[Any] = (retrieval, abstention, grounded_qa, translation, known_item)
