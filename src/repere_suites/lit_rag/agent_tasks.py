"""Agentic (tool-using) lit_rag tasks — RAG over the frozen OOI/COZI corpus.

The ``retrieval`` task in :mod:`inspect_tasks` is single-shot ``generate`` with
the candidate corpus described *inside the prompt*. This module is the
**RAG-agent** counterpart: the model is given only a query and must call the
``literature_search`` tool to retrieve candidates from the frozen corpus, then
submit a ranked list of stable ids. Scoring reuses the suite's deterministic
nDCG retrieval scorer (``lit_rag_scorer``), wrapped with
:func:`repere.agents.metrics.with_tool_metrics` so each sample also carries
the tool-use (harness-competence) axis.

Run::

    inspect eval src/repere_suites/lit_rag/agent_tasks.py@retrieval_agent \\
        --solver src/repere/agents/solver.py@lit_rag_react \\
        --model ollama/qwen2.5:7b

Gold ids must be document ids present in ``data/ooi_corpus.json``. When you
swap the seed corpus for the group's real OOI/COZI papers, update
``_QUERIES`` gold sets to match.
"""

from __future__ import annotations

import json
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample

from repere.agents.metrics import with_tool_metrics

from .inspect_tasks import lit_rag_scorer

# nDCG@5 over a ranked id list — the same scorer spec the YAML retrieval tasks
# carry, so the agent output is graded identically to the single-shot suite.
_RETRIEVAL_SPEC = {"name": "retrieval_metrics", "config": {"metric": "ndcg_at_k", "k": 5}}

# (task_id, query, gold-relevant ids, optional cutoff_date). Gold ids index
# into data/ooi_corpus.json. Keep gold sets tight and defensible.
_QUERIES: list[dict[str, Any]] = [
    {
        "id": "rag-ambient-noise-monitoring",
        "query": "ambient noise cross-correlation for crustal velocity monitoring offshore Cascadia",
        "gold": ["OOI-003", "OOI-004"],
        "cutoff_date": None,
    },
    {
        "id": "rag-hydrate-bubble-plumes",
        "query": "methane hydrate bubble plume dynamics at Southern Hydrate Ridge",
        "gold": ["OOI-002"],
        "cutoff_date": None,
    },
    {
        "id": "rag-ml-event-detection",
        "query": "machine learning detection of seismic events on the cabled array",
        "gold": ["OOI-008"],
        "cutoff_date": None,
    },
]


def _prompt(q: dict[str, Any]) -> str:
    cutoff = q.get("cutoff_date")
    cutoff_line = (
        f"Restrict to papers published on or before {cutoff}; pass "
        f'cutoff_date="{cutoff}" to literature_search.\n'
        if cutoff
        else ""
    )
    return (
        "Use the literature_search tool to retrieve candidate papers from the "
        "corpus, then rank them for the query:\n"
        f'  "{q["query"]}"\n'
        f"{cutoff_line}"
        "Submit a JSON array of document ids, most relevant first, "
        'e.g. ["OOI-003","OOI-007"]. Only include ids that appeared in a '
        "literature_search result."
    )


def _dataset() -> MemoryDataset:
    samples: list[Sample] = []
    for q in _QUERIES:
        samples.append(
            Sample(
                id=q["id"],
                input=_prompt(q),
                target=json.dumps(q["gold"], sort_keys=True),
                metadata={
                    "task_id": q["id"],
                    "kind": "retrieval",
                    "cutoff_date": q.get("cutoff_date"),
                    "scorer_spec": _RETRIEVAL_SPEC,
                },
            )
        )
    return MemoryDataset(samples=samples)


@task
def retrieval_agent() -> Task:
    """RAG retrieval as a tool-using agent, graded by nDCG@5 + tool-use axis.

    Solver is intentionally left unset here — pass ``--solver
    src/repere/agents/solver.py@lit_rag_react`` (or any solver that
    attaches ``literature_search`` + ``record_submit``) so the same task can
    be run across models on an identical tool surface.
    """
    return Task(
        dataset=_dataset(),
        scorer=with_tool_metrics(lit_rag_scorer()),
    )


__all__ = ["retrieval_agent"]
