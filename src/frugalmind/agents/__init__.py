"""Multi-step agent baselines for FrugalMind suites (P2.4).

The ReAct baseline lives in :mod:`frugalmind.agents.react` and the
InspectAI tool wrappers it uses live in :mod:`frugalmind.agents.tools`.
Both modules import ``inspect_ai`` lazily at *module load time*, so they
require the optional ``[eval]`` extra::

    pip install -e ".[eval]"

A static descriptor (``stalta_tools_dict``) is exposed here so tests
and docs can verify tool availability without importing ``inspect_ai``
at all — useful for environments without the eval extra installed.
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
