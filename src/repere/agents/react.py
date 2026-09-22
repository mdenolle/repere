"""ReAct-style baseline solver for the STA/LTA suites (P2.4).

InspectAI ships ``basic_agent`` — a ReAct-style loop that lets the model
choose between calling tools and submitting an answer. We wire our three
tools (``fdsn_get_waveforms``, ``python_session``, ``record_submit``)
into it under one Inspect ``@solver`` so any task can run as::

    inspect eval src/repere_suites/sta_lta/inspect_tasks.py@fetch_code \\
        --solver src/repere/agents/react.py@stalta_react \\
        --model anthropic/claude-haiku-4-5-20251001

This is the AstaBench reference comparison: same prompts, same scorers,
but a multi-step agent instead of single-shot ``generate``. With this
solver in place the cost-Pareto chart on the static site starts mapping
real budget-vs-quality trade-offs rather than just stub data.

Notes
-----

The solver is **provider-agnostic**: any model Inspect can talk to
works. The system prompt is brief and points the model at the three
tools; the suite prompts already carry the task specifics.
"""

from __future__ import annotations

from inspect_ai.solver import Solver, basic_agent, solver, system_message

from .tools import all_tools

_DEFAULT_SYSTEM_PROMPT = """\
You are an analyst running an STA/LTA seismic detection workflow. You
have three tools available:

  - fdsn_get_waveforms(network, station, location, channel, starttime,
    endtime, client="IRIS"): fetch a waveform window. Returns sampling
    rate, trace count, duration.
  - python_session(code, timeout_s=60): execute Python in an isolated
    subprocess sandbox. The sandbox exposes a `record(**kwargs)` helper
    that captures values for scoring; call it for any value the harness
    needs to see.
  - record_submit(answer): submit the final answer for scoring. Call
    this exactly once when you are confident. The string you pass is
    the answer that will be scored.

Rules:

  1. Stay in UTC throughout.
  2. Do not invent catalog ids, magnitudes, or origin times that are
     not in your tool results or the task input.
  3. For negative cases (no-event windows), do NOT hallucinate a
     detection. Reporting zero triggers is a correct answer.
  4. Always end with exactly one call to record_submit(...).
"""


@solver
def stalta_react(
    *,
    max_attempts: int = 1,
    message_limit: int | None = 24,
    system_prompt: str | None = None,
) -> Solver:
    """Inspect ``@solver`` that wraps ``basic_agent`` with Repère's tools.

    Parameters
    ----------
    max_attempts:
        How many submissions the model is allowed before the eval gives
        up. AstaBench typically allows 1; raise for noisier models.
    message_limit:
        Hard cap on the agent's message budget (a proxy for cost).
        Defaults to 24 which is plenty for the STA/LTA suites but
        catches a runaway tool-loop.
    system_prompt:
        Override the default system prompt above. Useful when wiring a
        skill prefix in front of the system message.
    """
    # _DEFAULT_SYSTEM_PROMPT is always non-empty, so the system message is
    # always installed. Callers that explicitly want no system message must
    # pass system_prompt="" — we treat that as "use the default" rather than
    # silently dropping the prompt, which would surprise downstream callers.
    prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT
    init: list[Solver] = [system_message(prompt)]

    return basic_agent(
        init=init,
        tools=all_tools(),
        max_attempts=max_attempts,
        message_limit=message_limit,
        submit_name="record_submit",
        submit_description="Submit the final answer for scoring.",
    )


__all__ = ["stalta_react"]
