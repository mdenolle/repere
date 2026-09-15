"""Generic ReAct solvers for FrugalMind agentic suites.

One scaffold — Inspect's ``basic_agent`` ReAct loop — parametrised by a
*named tool bundle* (from :mod:`frugalmind.agents.registry`) and a system
prompt. Every agentic suite gets a tool-using agent by calling
:func:`frugal_react`; no per-suite solver module is required, and because the
scaffold is held identical across models the open-vs-frontier comparison
measures the *model*, not a per-model harness.

Named specialisations live here too so ``inspect eval --solver`` has a stable
entry point:

    inspect eval src/frugalmind_suites/lit_rag/agent_tasks.py@retrieval_agent \\
        --solver src/frugalmind/agents/solver.py@lit_rag_react \\
        --model ollama/qwen2.5:7b

``inspect_ai`` is imported at module load, so this module needs the ``[eval]``
extra. The registry and metrics modules it builds on do not.
"""

from __future__ import annotations

from inspect_ai.solver import Solver, basic_agent, solver, system_message

from .registry import LIT_RAG_TOOLSET, STALTA_TOOLSET, _register_builtin_tools, resolve_tools

_LIT_RAG_SYSTEM_PROMPT = """\
You are a scientific literature analyst answering queries over a FROZEN
corpus of OOI Regional Cabled Array papers. You have two tools:

  - literature_search(query, cutoff_date=None, top_k=10): search the corpus.
    Returns candidate papers with stable ids (DOIs), titles, abstracts,
    first authors, journals and years. Rephrase and search again if the
    first results look off-topic.
  - record_submit(answer): submit the final answer for scoring.

Rules:

  1. Only cite or rank document ids that appear in a literature_search
     result. Never invent an id.
  2. If a cutoff_date is given in the task, pass it to literature_search and
     do NOT rely on any paper published after it.
  3. For a ranking task, submit a JSON array of ids best-first,
     e.g. ["10.1126/science.aah5563","10.1130/G39978.1"].
  4. For a question, answer in 2-4 sentences and cite each claim inline as
     [<doi>], quoting numbers and dates exactly as the abstract gives them.
  5. If nothing retrieved actually addresses the task — sharing vocabulary
     is not enough — submit exactly NO_RELEVANT_PAPERS and nothing else.
  6. Submit exactly once via record_submit(...).
"""


@solver
def frugal_react(
    *,
    tool_names: list[str] | None = None,
    system_prompt: str,
    max_attempts: int = 1,
    message_limit: int | None = 24,
    submit_name: str = "record_submit",
    submit_description: str = "Submit the final answer for scoring.",
) -> Solver:
    """Generic ReAct solver: wrap ``basic_agent`` around a named tool bundle.

    Parameters
    ----------
    tool_names:
        Registry names of the tools to attach (see
        :mod:`frugalmind.agents.registry`). Defaults to the STA/LTA bundle.
        Order is preserved in the tool list handed to Inspect.
    system_prompt:
        Full system prompt. Required — an agentic solver without task framing
        behaves unpredictably, so we do not guess a default here.
    max_attempts:
        Submissions allowed before the eval gives up. AstaBench uses 1; raise
        for noisier small models that fumble the submit call.
    message_limit:
        Hard cap on the agent's message budget (a cost proxy that also catches
        runaway tool-loops). ``None`` disables the cap.
    submit_name / submit_description:
        Name and help text of the terminal "submit" tool. Keep
        ``record_submit`` unless a suite deliberately renames it.
    """
    _register_builtin_tools()
    names = list(tool_names) if tool_names is not None else list(STALTA_TOOLSET)
    init: list[Solver] = [system_message(system_prompt)]

    return basic_agent(
        init=init,
        tools=resolve_tools(names),
        max_attempts=max_attempts,
        message_limit=message_limit,
        submit_name=submit_name,
        submit_description=submit_description,
    )


@solver
def lit_rag_react(
    *,
    max_attempts: int = 1,
    message_limit: int | None = 24,
    system_prompt: str | None = None,
) -> Solver:
    """Literature-RAG specialisation: ``literature_search`` + ``record_submit``.

    The agent retrieves over the frozen corpus and submits a ranked id list
    (or a grounded, cited answer), scored by the lit_rag suite scorers.
    """
    return frugal_react(
        tool_names=list(LIT_RAG_TOOLSET),
        system_prompt=system_prompt or _LIT_RAG_SYSTEM_PROMPT,
        max_attempts=max_attempts,
        message_limit=message_limit,
    )


__all__ = ["frugal_react", "lit_rag_react"]
