"""Descriptor-only contract for the ReAct baseline (P2.4).

This module deliberately does **not** import ``inspect_ai``. Its single
test pins the contract that ``repere.agents`` exposes a usable
``stalta_tools_dict()`` even in environments that haven't installed the
``[eval]`` extra.

The inspect_ai-dependent ReAct tests live in ``tests/test_react_agent.py``
and are gated on the extra being present.
"""

from __future__ import annotations

from repere.agents import stalta_tools_dict


def test_stalta_tools_dict_lists_exactly_the_three_react_tools():
    """The static descriptor is the source of truth for tool availability
    and must remain importable without ``inspect_ai``."""
    descriptor = stalta_tools_dict()
    assert set(descriptor) == {"fdsn_get_waveforms", "python_session", "record_submit"}
    # Each value is a short human-readable description.
    for name, desc in descriptor.items():
        assert isinstance(desc, str) and desc, f"{name}: description must be non-empty"
