"""InspectAI tool wrappers for the STA/LTA ReAct baseline (P2.4).

Three tools, all stateless and provider-agnostic so they work with any
InspectAI model backend (Anthropic, OpenAI, OpenAI-compatible, Ollama):

  - ``fdsn_get_waveforms`` — fetch a seismic waveform window via ObsPy /
    FDSN. ObsPy is in the optional ``[geo]`` extra; when it's missing the
    tool returns a structured error so the agent can keep going.
  - ``python_session``    — execute a Python snippet inside the existing
    STA/LTA sandbox (`run_snippet` from sta_lta/sandbox.py). The sandbox
    is a subprocess with a timeout — P2.2 will upgrade it to a Docker
    image; the tool's surface is unchanged.
  - ``record_submit``     — accept the agent's final answer for scoring.
    Matches the ``record(...)`` helper the suite prompts already
    instruct the model to call from generated code; here it's a tool the
    agent calls in conversation rather than from within a Python session.

All three are wrapped with ``@tool`` so InspectAI's ``basic_agent`` can
schedule them. They never raise — failures are returned as strings so
the agent can read and react to them.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from inspect_ai.tool import Tool, tool

# Lazy import obspy inside the tool body so the package stays importable
# when the [geo] extra isn't installed.


@tool
def fdsn_get_waveforms() -> Tool:
    """ObsPy FDSN waveform fetch as an Inspect tool.

    Args (per call):
        network, station, location, channel: SEED codes for the channel.
        starttime, endtime: ISO-8601 UTC strings.
        client: FDSN service name (default 'IRIS'); 'EARTHSCOPE' also accepted.

    Returns a JSON string with `{"ok": true, "n_traces": int,
    "sampling_rate_hz": float, "duration_s": float, "preview": str}` on
    success, or `{"ok": false, "error": "..."}` on failure.
    """

    async def execute(
        network: str,
        station: str,
        location: str,
        channel: str,
        starttime: str,
        endtime: str,
        client: str = "IRIS",
    ) -> str:
        try:
            from obspy import UTCDateTime
            from obspy.clients.fdsn import Client
        except ImportError:
            return json.dumps(
                {
                    "ok": False,
                    "error": "obspy is not installed; run `pip install -e \".[geo]\"`",
                }
            )

        def _blocking_fetch():
            # Client(...) and get_waveforms(...) are synchronous network I/O.
            # Run them in a worker thread so we don't stall Inspect's event
            # loop while other in-flight samples make progress.
            c = Client(client, timeout=60)
            t_start = UTCDateTime(starttime)
            t_end = UTCDateTime(endtime)
            return c.get_waveforms(
                network=network,
                station=station,
                location=location,
                channel=channel,
                starttime=t_start,
                endtime=t_end,
                attach_response=False,
            )

        try:
            st = await asyncio.to_thread(_blocking_fetch)
        except Exception as exc:
            return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

        if not st:
            return json.dumps({"ok": False, "error": "empty stream returned"})

        tr = st[0]
        return json.dumps(
            {
                "ok": True,
                "n_traces": len(st),
                "sampling_rate_hz": float(tr.stats.sampling_rate),
                "duration_s": float(tr.stats.endtime - tr.stats.starttime),
                "preview": str(st)[:600],
                "client": client,
            }
        )

    return execute


@tool
def python_session() -> Tool:
    """Execute a Python snippet in the STA/LTA subprocess sandbox.

    The sandbox is the same one used by the suite scorers
    (``frugalmind_suites.sta_lta.sandbox.run_snippet``): a fresh
    subprocess with a timeout, a ``record(**kwargs)`` helper that
    captures values for scoring, and a clean output directory. P2.2
    will swap the subprocess for a pinned Docker image; the tool's
    surface stays the same.

    Args (per call):
        code: Python source. May call ``record(key=value, …)``; the
              snippet's stdout, stderr, and recorded artefacts are
              returned to the model.
        timeout_s: per-call timeout in seconds. Default 60.

    Returns a JSON string with stdout, stderr, returncode, timed_out,
    and the captured artefacts dict.
    """

    async def execute(code: str, timeout_s: float = 60.0) -> str:
        # Import inside the tool body so importing this module doesn't
        # require frugalmind_suites to be on sys.path at import time.
        from frugalmind_suites.sta_lta.sandbox import run_snippet

        # ``run_snippet`` is built on blocking ``subprocess.run`` calls,
        # which would block Inspect's event loop for the snippet's full
        # duration. Offload to a worker thread so other in-flight samples
        # can keep making progress while this snippet executes.
        result = await asyncio.to_thread(run_snippet, code, timeout_s=float(timeout_s))
        payload = {
            "ok": result.ok,
            "stdout": (result.stdout or "")[-2000:],  # cap to last 2KB
            "stderr": (result.stderr or "")[-2000:],
            "returncode": result.returncode,
            "timed_out": result.timed_out,
            "artifacts": result.artifacts or {},
            "artifact_files": [str(f) for f in (result.artifact_files or [])],
        }
        return json.dumps(payload)

    return execute


@tool
def record_submit() -> Tool:
    """Submit the final answer for scoring.

    This mirrors AstaBench's ``submit`` pattern and our existing
    ``record(...)`` helper that suite prompts already use. The agent
    calls this tool exactly once when it's ready to be scored. The
    string argument is what the suite scorer compares against the gold.

    For the JSON-extraction suite the agent should pass a JSON string;
    for code-generation suites it should pass the generated code block;
    for the report suite, the one-paragraph report text. Whatever it
    passes flows through unchanged to ``state.output.completion``.
    """

    async def execute(answer: str) -> str:
        # The Inspect basic_agent reads the *string* return value as the
        # submission. We echo it back verbatim so the scorer sees exactly
        # what the agent intended to submit.
        return str(answer)

    return execute


# Public surface — keep alphabetised for diff stability.
__all__ = [
    "fdsn_get_waveforms",
    "python_session",
    "record_submit",
]


def all_tools() -> list[Tool]:
    """Convenience: instantiate every default tool. Used by the ReAct solver."""
    return [fdsn_get_waveforms(), python_session(), record_submit()]


def stalta_tools_dict() -> dict[str, Any]:
    """Static descriptor used by tests + docs to verify tool availability
    without paying the import cost of `inspect_ai` everywhere."""
    return {
        "fdsn_get_waveforms": "ObsPy FDSN waveform fetch (network, station, channel, time window)",
        "python_session": "Run a Python snippet in the STA/LTA subprocess sandbox",
        "record_submit": "Submit the final answer for scoring",
    }
