"""InspectAI tool wrapper for corpus-backed literature retrieval.

``literature_search`` is the RAG tool the lit_rag agent attaches to. It is a
thin Inspect ``@tool`` over the pure, deterministic search in
:mod:`repere.agents.literature` — so the model retrieves over a *frozen*
corpus with stable ids and an enforced cutoff, never the live web. See that
module's docstring for why web search is the wrong primitive here.

The tool never raises: failures come back as ``{"ok": false, "error": ...}``
strings so the agent can read and react to them, matching the STA/LTA tools.
Registration into the shared tool registry is lazy (in
:mod:`repere.agents.registry`) so this module — and ``inspect_ai`` — is
only imported when a solver actually resolves the tool.
"""

from __future__ import annotations

import asyncio
import json

from inspect_ai.tool import Tool, tool

from .literature import load_corpus, search_corpus


@tool
def literature_search() -> Tool:
    """Search a frozen scientific corpus; return ranked papers with stable ids.

    Args (per call):
        query: free-text query.
        cutoff_date: optional ISO date "YYYY-MM-DD". Papers published after it
            are excluded from results (the AstaBench date-cutoff contract).
        top_k: max number of hits to return (default 10).

    Returns a JSON string ``{"ok": true, "n": int, "results": [{id, title,
    abstract, year, doi, score}, ...]}`` best-first, or
    ``{"ok": false, "error": "..."}`` on failure. Only ids that appear in a
    result may be cited or ranked in the final answer.
    """

    async def execute(query: str, cutoff_date: str | None = None, top_k: int = 10) -> str:
        try:
            # load_corpus does blocking file I/O; keep it off the event loop
            # so concurrent samples keep progressing.
            docs = await asyncio.to_thread(load_corpus)
            results = search_corpus(query, docs, cutoff_date=cutoff_date, top_k=int(top_k))
        except Exception as exc:  # never raise into the agent loop
            return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return json.dumps({"ok": True, "n": len(results), "results": results})

    return execute


__all__ = ["literature_search"]
