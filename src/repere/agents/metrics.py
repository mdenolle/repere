"""Tool-use metrics — the *harness-competence* axis of an agentic eval.

Repère scores agentic suites on two independent axes:

1. **Task correctness** — is the submitted artifact right? Answered by the
   suite's deterministic scorer (e.g. ``stalta_scorer``, ``lit_rag_scorer``).
2. **Tool-use competence** — could the model *drive the harness* at all? Did
   it emit well-formed tool calls, converge, and submit?

The two must stay separate. A small open model that scores 0 because it never
produced a valid ``record_submit`` call is failing differently from one that
submitted a wrong answer — and a router that conflates them will mis-route.
This module extracts axis 2 from an Inspect ``TaskState`` so it can ride along
in ``Score.metadata`` and land in telemetry ``extra`` next to the score.

The core function, :func:`tool_use_stats`, is pure and duck-typed on the
message list, so it is unit-testable without a live model or the ``[eval]``
extra installed.
"""

from __future__ import annotations

from typing import Any


def tool_use_stats(state: Any, *, submit_name: str = "record_submit") -> dict[str, Any]:
    """Summarise the agent's tool usage over a completed sample.

    Parameters
    ----------
    state:
        An Inspect ``TaskState`` (or any object exposing ``.messages``).
        Each assistant message may carry ``.tool_calls``; each tool result
        message may carry an ``.error``. Both are read defensively.
    submit_name:
        Name of the terminal submit tool, so we can report whether the
        agent actually submitted.

    Returns
    -------
    dict with:
        ``n_tool_calls``    total tool invocations (a cost/effort proxy).
        ``n_tool_errors``   tool results that came back as errors.
        ``distinct_tools``  sorted list of tool names the agent used.
        ``submitted``       whether ``submit_name`` was ever called.
        ``converged``       submitted **and** no error on the last tool call
                            — a cheap "clean finish" flag.
    """
    messages = getattr(state, "messages", None) or []

    n_tool_calls = 0
    n_tool_errors = 0
    distinct: set[str] = set()
    submitted = False
    last_call_errored = False

    for msg in messages:
        # Assistant messages hold the tool *calls* the model requested.
        for call in getattr(msg, "tool_calls", None) or []:
            n_tool_calls += 1
            name = getattr(call, "function", None) or getattr(call, "name", None)
            if name:
                distinct.add(str(name))
                if str(name) == submit_name:
                    submitted = True
            # A malformed / unparseable argument payload is a harness failure,
            # not a task failure — count it toward tool errors.
            if getattr(call, "parse_error", None):
                n_tool_errors += 1

        # Tool *result* messages (role == "tool") may carry an execution error.
        if getattr(msg, "role", None) == "tool":
            err = getattr(msg, "error", None)
            if err is not None:
                n_tool_errors += 1
                last_call_errored = True
            else:
                last_call_errored = False

    return {
        "n_tool_calls": n_tool_calls,
        "n_tool_errors": n_tool_errors,
        "distinct_tools": sorted(distinct),
        "submitted": submitted,
        "converged": submitted and not last_call_errored,
    }


def with_tool_metrics(inner_scorer: Any, *, submit_name: str = "record_submit") -> Any:
    """Wrap an Inspect scorer so each ``Score`` also carries tool-use stats.

    Use this to keep the two axes together with zero changes to the suite
    scorer::

        from repere.agents.metrics import with_tool_metrics
        Task(dataset=..., solver=stalta_react(),
             scorer=with_tool_metrics(stalta_scorer()))

    The wrapped scorer's ``value`` (axis 1, correctness) is untouched; the
    tool-use dict (axis 2) is merged under ``Score.metadata['tool_use']``,
    from where a telemetry sink can lift it into the sample's ``extra`` field.

    Requires the ``[eval]`` extra (imports ``inspect_ai`` lazily).
    """
    from inspect_ai.scorer import Score, Target, accuracy, mean, scorer
    from inspect_ai.solver import TaskState

    @scorer(metrics=[mean(), accuracy()])
    def _scored() -> Any:
        async def score(state: TaskState, target: Target) -> Score:
            base = await inner_scorer(state, target)
            meta = dict(getattr(base, "metadata", None) or {})
            meta["tool_use"] = tool_use_stats(state, submit_name=submit_name)
            return Score(
                value=base.value,
                answer=getattr(base, "answer", None),
                explanation=getattr(base, "explanation", None),
                metadata=meta,
            )

        return score

    return _scored()


__all__ = ["tool_use_stats", "with_tool_metrics"]
