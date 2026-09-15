"""Agentic (tool-using) lit_rag tasks — RAG over the frozen OOI-RCA corpus.

The tasks in :mod:`inspect_tasks` are single-shot ``generate`` with the
candidate papers described *inside the prompt*. This module is the
**RAG-agent** counterpart: the model is given only the query and must call
the ``literature_search`` tool to retrieve candidates from the frozen corpus,
then submit a ranked list of DOIs, a cited answer, or the abstention
sentinel. Scoring reuses the suite's deterministic scorers, wrapped with
:func:`frugalmind.agents.metrics.with_tool_metrics` so each sample also
carries the tool-use (harness-competence) axis.

Run::

    inspect eval src/frugalmind_suites/lit_rag/agent_tasks.py@retrieval_agent \\
        --solver src/frugalmind/agents/solver.py@lit_rag_react \\
        --model ollama/qwen2.5:7b

    # the deployed system's own retriever, no LLM: the floor every agent
    # must clear to justify its cost
    inspect eval src/frugalmind_suites/lit_rag/agent_tasks.py@retrieval_agent \\
        --solver src/frugalmind_suites/lit_rag/agent_tasks.py@lexical_retrieval_baseline \\
        --model none/none

Gold ids are DOIs in ``data/ooi_rca_corpus.json``; the same ids the deployed
aRCADA index cites (``paper::<doi>``).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import ModelOutput
from inspect_ai.solver import Generate, Solver, TaskState, solver

from frugalmind.agents.literature import load_corpus, search_corpus
from frugalmind.agents.metrics import with_tool_metrics

from .inspect_tasks import lit_rag_scorer
from .items import _corpus_for, _load_truth
from .scorers import ABSTAIN_SENTINEL

# nDCG@5 over the submitted DOI list — recall-oriented, since an agent that
# searches can return more than the shortlist a single-shot prompt shows.
_RETRIEVAL_SPEC = {"name": "retrieval_metrics", "config": {"metric": "ndcg_at_k", "k": 5}}


def _cutoff_line(item: dict[str, Any]) -> str:
    cutoff = item.get("cutoff_date")
    if not cutoff:
        return ""
    return (
        f"Restrict to papers published on or before {cutoff}; pass "
        f'cutoff_date="{cutoff}" to literature_search.\n'
    )


def _retrieval_prompt(item: dict[str, Any]) -> str:
    return (
        "Use the literature_search tool to retrieve candidate papers from the "
        "OOI Regional Cabled Array corpus, then rank them for the question:\n"
        f'  "{" ".join(item["query"].split())}"\n'
        f"{_cutoff_line(item)}"
        "Submit a JSON array of document ids (DOIs), most relevant first, "
        'e.g. ["10.1126/science.aah5563","10.1130/G39978.1"]. Only include ids '
        "that appeared in a literature_search result."
    )


def _abstention_prompt(item: dict[str, Any], sentinel: str) -> str:
    return (
        "Use the literature_search tool to look for papers in the OOI Regional "
        "Cabled Array corpus that address the question:\n"
        f'  "{" ".join(item["query"].split())}"\n'
        f"{_cutoff_line(item)}"
        "If one or more retrieved papers address it, submit a JSON array of "
        "their ids (DOIs), most relevant first. If none does — a paper that "
        "merely shares vocabulary with the question does not count — submit "
        f"exactly {sentinel} and nothing else."
    )


def _grounded_qa_prompt(item: dict[str, Any], sentinel: str) -> str:
    return (
        "Use the literature_search tool to find papers in the OOI Regional "
        "Cabled Array corpus, then answer the question in 2-4 sentences using "
        "only what the retrieved abstracts say:\n"
        f'  "{" ".join(item["query"].split())}"\n'
        f"{_cutoff_line(item)}"
        "Cite the source for every claim inline by putting its id in square "
        "brackets, e.g. [10.1126/science.aah5563]. Quote numbers and dates "
        "exactly as the abstract gives them. If the retrieved papers do not "
        f"contain the answer, submit exactly {sentinel} and nothing else."
    )


def _dataset(kind: str, split: str) -> MemoryDataset:
    meta, items = _load_truth(split=split)
    sentinel = meta.get("sentinel", ABSTAIN_SENTINEL)
    corpus_ids = [d.id for d in _corpus_for(meta)]
    samples: list[Sample] = []
    for it in items:
        if kind == "retrieval" and it["kind"] != "known_item":
            continue
        if kind == "abstention" and not (
            it["kind"] == "abstention"
            or (it["kind"] == "known_item" and it.get("abstention_control"))
        ):
            continue
        if kind == "grounded_qa" and it["kind"] != "grounded_qa":
            continue
        answerable = bool(it.get("answerable", True))
        gold = [str(g) for g in it.get("gold") or []]
        if kind == "retrieval":
            prompt, spec = _retrieval_prompt(it), _RETRIEVAL_SPEC
        elif kind == "abstention":
            prompt = _abstention_prompt(it, sentinel)
            spec = {"name": "abstention", "config": {"answerable": answerable}}
        else:
            prompt = _grounded_qa_prompt(it, sentinel)
            if answerable:
                # Any corpus id is a valid citation for an agent that searched;
                # relevance is still judged against the gold.
                spec = {
                    "name": "attribution",
                    "config": {
                        "valid_sources": corpus_ids,
                        "relevant_sources": gold,
                        "required_terms": list(it.get("required_terms") or []),
                        "forbidden_terms": list(it.get("forbidden_terms") or []),
                    },
                }
            else:
                spec = {"name": "abstention", "config": {"answerable": False}}
        md = {
            "task_id": it["id"],
            "kind": it["kind"],
            "query": " ".join(it["query"].split()),
            "answerable": answerable,
            "cutoff_date": it.get("cutoff_date"),
            "sentinel": sentinel,
            "scorer_spec": spec,
        }
        md.update(it.get("metadata") or {})
        samples.append(
            Sample(id=it["id"], input=prompt, target=json.dumps(gold, sort_keys=True), metadata=md)
        )
    return MemoryDataset(samples=samples)


@solver
def lexical_retrieval_baseline(top_k: int = 5) -> Solver:
    """The deployed retriever alone: ``search_corpus`` top-k, no model call.

    Runs through the same task and scorer as every agent, so the "do nothing
    clever" row sits on the same axes. It never abstains (BM25-style search
    always returns its best matches), which is exactly the behaviour the
    abstention suite is meant to expose.
    """

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        md = state.metadata or {}
        docs = await asyncio.to_thread(load_corpus)
        hits = search_corpus(
            str(md.get("query", state.input_text)),
            docs,
            cutoff_date=md.get("cutoff_date"),
            top_k=top_k,
        )
        state.output = ModelOutput.from_content(
            model="baseline/lexical", content=json.dumps([h["id"] for h in hits])
        )
        state.completed = True
        return state

    return solve


@task
def retrieval_agent(split: str = "validation", epochs: int = 1) -> Task:
    """RAG retrieval as a tool-using agent, graded by nDCG@5 + tool-use axis.

    Solver is intentionally left unset — pass ``--solver
    src/frugalmind/agents/solver.py@lit_rag_react`` (or
    ``@lexical_retrieval_baseline`` from this module) so the same task runs
    across models and baselines on an identical tool surface.
    """
    return Task(
        dataset=_dataset("retrieval", split),
        scorer=with_tool_metrics(lit_rag_scorer()),
        epochs=epochs,
    )


@task
def abstention_agent(split: str = "validation", epochs: int = 1) -> Task:
    """Search, then decide: cite what is relevant or submit the sentinel."""
    return Task(
        dataset=_dataset("abstention", split),
        scorer=with_tool_metrics(lit_rag_scorer()),
        epochs=epochs,
    )


@task
def grounded_qa_agent(split: str = "validation", epochs: int = 1) -> Task:
    """Search, then answer with DOI citations; attribution breakdown per sample."""
    return Task(
        dataset=_dataset("grounded_qa", split),
        scorer=with_tool_metrics(lit_rag_scorer()),
        epochs=epochs,
    )


__all__ = [
    "abstention_agent",
    "grounded_qa_agent",
    "lexical_retrieval_baseline",
    "retrieval_agent",
]
