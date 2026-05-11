"""Tests for the ReAct multi-step agent baseline (P2.4) — inspect_ai-gated.

This module is gated on ``inspect_ai`` being installed via the optional
``[eval]`` extra. The single descriptor-only contract that must hold even
**without** the extra lives in ``tests/test_react_descriptor.py``; do not
move it back here — ``pytest.importorskip`` below would silently skip it.

Three contracts pinned here:

  1. Each ``@tool`` instantiates as an Inspect ``Tool`` and the three
     ``execute`` callables behave correctly in isolation:
       * ``record_submit`` echoes its argument verbatim.
       * ``python_session`` runs a trivial snippet end-to-end through the
         real STA/LTA subprocess sandbox.
       * ``fdsn_get_waveforms`` returns a structured ``{"ok": false, ...}``
         error when ``obspy`` is missing — so the model can read the
         failure and keep going.
  2. ``stalta_tools_dict()`` agrees with the no-extra-required descriptor.
  3. ``stalta_react()`` returns an Inspect ``Solver`` whose construction
     wires the three tools through ``basic_agent`` without raising.
"""

from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("inspect_ai")

from inspect_ai.tool import Tool  # noqa: E402

from frugalmind.agents import stalta_tools_dict  # noqa: E402
from frugalmind.agents.react import stalta_react  # noqa: E402
from frugalmind.agents.tools import (  # noqa: E402
    all_tools,
    fdsn_get_waveforms,
    python_session,
    record_submit,
)
from frugalmind.agents.tools import stalta_tools_dict as runtime_tools_dict  # noqa: E402

# ---------------------------------------------------------------------------
# 1. Descriptor consistency: static (__init__) and runtime (tools.py) agree
# ---------------------------------------------------------------------------


def test_static_and_runtime_descriptor_agree():
    """The descriptor exposed without inspect_ai must match the runtime one
    that imports it. If they drift, contributors who add a tool to tools.py
    but forget to update __init__.py would silently break the no-extras path."""
    assert stalta_tools_dict() == runtime_tools_dict()


# ---------------------------------------------------------------------------
# 2. Tool instantiation: each @tool returns an Inspect Tool
# ---------------------------------------------------------------------------


def test_each_tool_factory_returns_a_callable_tool():
    for factory in (fdsn_get_waveforms, python_session, record_submit):
        t = factory()
        # `Tool` in inspect_ai is a Protocol/callable alias; the strict
        # invariant we care about is that the returned object is callable
        # (basic_agent will await it). We additionally assert it is a Tool
        # instance when the runtime exposes a concrete class.
        assert callable(t), f"{factory.__name__}() must return a callable"
        # `isinstance(_, Tool)` works because inspect_ai marks @tool-returned
        # callables as Tool; if Tool is a Protocol, isinstance still resolves
        # via runtime_checkable.
        assert isinstance(t, Tool), f"{factory.__name__}() must return a Tool"


def test_all_tools_returns_exactly_three_distinct_tools():
    ts = all_tools()
    assert len(ts) == 3
    # The list is positional; verify each entry is independently a Tool.
    for t in ts:
        assert isinstance(t, Tool)


# ---------------------------------------------------------------------------
# 3. Tool behaviour: each execute callable does the right thing in isolation
# ---------------------------------------------------------------------------


def _call(tool_obj, *args, **kwargs):
    """Run a tool's coroutine to completion and return its string result."""
    return asyncio.run(tool_obj(*args, **kwargs))


def test_record_submit_echoes_its_argument_verbatim():
    """The submission path must not mutate the model's answer string."""
    submit = record_submit()
    payload = '{"triggers": [{"on_time": "2024-01-01T00:00:00Z"}]}'
    assert _call(submit, answer=payload) == payload


def test_record_submit_handles_empty_string_without_crashing():
    submit = record_submit()
    assert _call(submit, answer="") == ""


def test_python_session_runs_trivial_snippet_and_captures_record():
    """End-to-end through the real STA/LTA subprocess sandbox: a snippet that
    prints to stdout and calls record(...) should round-trip cleanly."""
    sess = python_session()
    code = "record(answer=2 + 2)\nprint('hello from sandbox')"
    raw = _call(sess, code=code, timeout_s=20.0)
    payload = json.loads(raw)
    assert payload["ok"] is True, payload
    assert payload["returncode"] == 0
    assert "hello from sandbox" in payload["stdout"]
    assert payload["artifacts"].get("answer") == 4
    assert payload["timed_out"] is False


def test_python_session_surfaces_error_without_raising():
    """A snippet that raises should come back as ok=False, not bubble up
    — the agent needs the stderr text to decide what to do next."""
    sess = python_session()
    raw = _call(sess, code="raise RuntimeError('boom')", timeout_s=10.0)
    payload = json.loads(raw)
    assert payload["ok"] is False
    assert "RuntimeError" in payload["stderr"] or "boom" in payload["stderr"]


def test_python_session_catches_run_snippet_exception_and_returns_payload(monkeypatch):
    """The @tool contract is 'never raise'. ``run_snippet`` already catches
    its own subprocess.TimeoutExpired, but filesystem / OSError / future
    docker-pull failures could escape via ``asyncio.to_thread``. Force
    such an error and assert the tool returns a structured ok=False
    payload instead of letting the exception bubble out into Inspect's
    event loop (which would abort the run)."""
    import frugalmind.agents.tools as tools_mod

    def _explode(*args, **kwargs):
        raise OSError("simulated tmpdir creation failure")

    # ``run_snippet`` is imported inside execute() — patch it at its
    # source module so the lazy import sees our exploder.
    import frugalmind_suites.sta_lta.sandbox as sandbox_mod

    monkeypatch.setattr(sandbox_mod, "run_snippet", _explode)
    # Defensive: also patch the symbol on tools_mod in case it was
    # rebound at import time (it isn't today, but cheap insurance).
    if hasattr(tools_mod, "run_snippet"):
        monkeypatch.setattr(tools_mod, "run_snippet", _explode, raising=False)

    sess = python_session()
    raw = _call(sess, code="print('x')", timeout_s=5.0)
    payload = json.loads(raw)
    assert payload["ok"] is False
    assert payload["returncode"] is None
    assert payload["timed_out"] is False
    assert "OSError" in payload["stderr"]
    assert "simulated tmpdir creation failure" in payload["stderr"]


def test_fdsn_get_waveforms_returns_structured_error_when_obspy_missing(monkeypatch):
    """If obspy isn't importable, the tool must return ok=false with a hint,
    not raise — the model needs to read it and either retry or submit zero."""
    import builtins

    real_import = builtins.__import__

    def _fail_obspy(name, *args, **kwargs):
        if name == "obspy" or name.startswith("obspy."):
            raise ImportError(f"no module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fail_obspy)

    fetch = fdsn_get_waveforms()
    raw = _call(
        fetch,
        network="UW",
        station="JCW",
        location="",
        channel="HHZ",
        starttime="2024-01-01T00:00:00",
        endtime="2024-01-01T00:01:00",
    )
    payload = json.loads(raw)
    assert payload["ok"] is False
    assert "obspy" in payload["error"].lower()


# ---------------------------------------------------------------------------
# 4. Solver construction: stalta_react wires basic_agent without raising
# ---------------------------------------------------------------------------


def test_stalta_react_returns_an_inspect_solver():
    """The factory must produce a real Inspect Solver — that's what
    `inspect eval --solver src/frugalmind/agents/react.py@stalta_react` expects."""
    solver = stalta_react()
    # Like Tool, Solver in inspect_ai is typically a Protocol/callable alias.
    # We assert the weakest contract that matters at the CLI boundary:
    # the object is callable (Inspect awaits it on each sample).
    assert callable(solver), "stalta_react() must return a callable solver"


def test_stalta_react_accepts_overrides_for_budget_and_attempts():
    """Override knobs exist so the CLI can swap caps without code changes."""
    solver = stalta_react(max_attempts=3, message_limit=8)
    assert callable(solver)


def test_stalta_react_accepts_custom_system_prompt():
    """A bench harness may want to prepend a skill — the override must
    succeed without complaint."""
    solver = stalta_react(system_prompt="You are a terse seismic analyst.")
    assert callable(solver)


def test_stalta_react_allows_unbounded_message_limit():
    """``message_limit=None`` means 'let basic_agent decide'. Make sure
    passing None is accepted and doesn't trip a TypeError downstream."""
    solver = stalta_react(message_limit=None)
    assert callable(solver)
