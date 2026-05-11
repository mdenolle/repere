"""Multi-step agent baselines for FrugalMind suites (P2.4).

The ReAct baseline lives in :mod:`frugalmind.agents.react` and the
InspectAI tool wrappers it uses live in :mod:`frugalmind.agents.tools`.
**Both submodules import** ``inspect_ai`` **at module top level**, so
importing either of them requires the optional ``[eval]`` extra::

    pip install -e ".[eval]"

This package (:mod:`frugalmind.agents`) itself has no eager dependency
on ``inspect_ai`` — it only pulls in the standard library plus the
static descriptor below. Tests and docs that just need to verify tool
availability can call :func:`stalta_tools_dict` without paying the
cost of installing ``inspect_ai`` or any of its transitive deps.
"""

from __future__ import annotations

from typing import Any


def stalta_tools_dict() -> dict[str, Any]:
    """Static descriptor of the STA/LTA ReAct tool surface.

    Mirrors the dict produced by :func:`frugalmind.agents.tools.stalta_tools_dict`
    but does not import ``inspect_ai`` — safe to call in environments
    without the ``[eval]`` extra installed. Kept in lockstep with
    ``tools.py``; if a tool is added or removed there, update both.
    """
    return {
        "fdsn_get_waveforms": (
            "ObsPy FDSN waveform fetch (network, station, channel, time window)"
        ),
        "python_session": "Run a Python snippet in the STA/LTA subprocess sandbox",
        "record_submit": "Submit the final answer for scoring",
    }


__all__ = ["stalta_tools_dict"]
