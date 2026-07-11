"""Tests for the tool registry, generic solver, and two-axis metrics.

Exercise the extension points in ``docs/agentic_eval.md``: registering a tool
by name, resolving a bundle, the generic ``frugal_react`` honouring a custom
tool list, and ``tool_use_stats`` extracting the harness-competence axis from a
duck-typed message list (no live model, no ``inspect_ai`` needed).
"""

from __future__ import annotations

import importlib.util

import pytest

from frugalmind.agents import metrics, registry

_HAS_INSPECT = importlib.util.find_spec("inspect_ai") is not None


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


def test_builtin_tools_registered_with_descriptions():
    d = registry.tools_dict()
    for name in (*registry.STALTA_TOOLSET, "literature_search"):
        assert name in d
        assert d[name]  # non-empty description


def test_list_tools_is_sorted():
    names = registry.list_tools()
    assert names == sorted(names)


def test_lit_rag_toolset_names_are_registered():
    for name in registry.LIT_RAG_TOOLSET:
        assert name in registry.list_tools()


def test_get_spec_unknown_name_lists_available():
    with pytest.raises(KeyError) as exc:
        registry.get_spec("does_not_exist")
    assert "record_submit" in str(exc.value)


def test_duplicate_registration_raises():
    with pytest.raises(ValueError):
        registry.register(
            registry.ToolSpec(
                "record_submit",
                registry._lazy_factory("frugalmind.agents.tools", "record_submit"),
                "dup",
            )
        )


def test_register_tool_decorator_adds_and_returns_factory():
    marker = object()

    @registry.register_tool("unit_test_tool", "a throwaway tool for tests")
    def _factory():
        return marker

    try:
        assert _factory() is marker  # returned unchanged
        assert "unit_test_tool" in registry.list_tools()
        assert registry.resolve_tools(["unit_test_tool"]) == [marker]
    finally:
        registry._REGISTRY.pop("unit_test_tool", None)


@pytest.mark.skipif(not _HAS_INSPECT, reason="requires the [eval] extra")
def test_resolve_tools_builds_distinct_bundle():
    bundle = registry.resolve_tools(list(registry.STALTA_TOOLSET))
    assert len(bundle) == 3
    assert len({id(t) for t in bundle}) == 3


# --------------------------------------------------------------------------- #
# Generic + specialised solvers
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not _HAS_INSPECT, reason="requires the [eval] extra")
def test_frugal_react_accepts_custom_tool_list():
    from frugalmind.agents.solver import frugal_react

    solver = frugal_react(
        tool_names=["python_session", "record_submit"],
        system_prompt="You are a terse analyst.",
    )
    assert callable(solver)


@pytest.mark.skipif(not _HAS_INSPECT, reason="requires the [eval] extra")
def test_lit_rag_react_constructs():
    from frugalmind.agents.solver import lit_rag_react

    assert callable(lit_rag_react())


# --------------------------------------------------------------------------- #
# Two-axis metrics — pure, no inspect_ai needed
# --------------------------------------------------------------------------- #


class _Call:
    def __init__(self, function=None, parse_error=None):
        self.function = function
        self.parse_error = parse_error


class _Msg:
    def __init__(self, role="assistant", tool_calls=None, error=None):
        self.role = role
        self.tool_calls = tool_calls
        self.error = error


class _State:
    def __init__(self, messages):
        self.messages = messages


def test_tool_use_stats_clean_submit():
    state = _State(
        [
            _Msg(tool_calls=[_Call("literature_search")]),
            _Msg(role="tool", error=None),
            _Msg(tool_calls=[_Call("record_submit")]),
            _Msg(role="tool", error=None),
        ]
    )
    stats = metrics.tool_use_stats(state)
    assert stats["n_tool_calls"] == 2
    assert stats["n_tool_errors"] == 0
    assert stats["submitted"] is True
    assert stats["converged"] is True
    assert stats["distinct_tools"] == ["literature_search", "record_submit"]


def test_tool_use_stats_counts_errors_and_parse_failures():
    state = _State(
        [
            _Msg(tool_calls=[_Call("literature_search", parse_error="bad json")]),
            _Msg(role="tool", error="Traceback ..."),
        ]
    )
    stats = metrics.tool_use_stats(state)
    assert stats["n_tool_errors"] == 2  # malformed args + tool-result error
    assert stats["submitted"] is False
    assert stats["converged"] is False


def test_tool_use_stats_never_submitted():
    state = _State([_Msg(tool_calls=[_Call("literature_search")])])
    stats = metrics.tool_use_stats(state)
    assert stats["submitted"] is False
    assert stats["converged"] is False


def test_tool_use_stats_empty_state():
    assert metrics.tool_use_stats(_State([])) == {
        "n_tool_calls": 0,
        "n_tool_errors": 0,
        "distinct_tools": [],
        "submitted": False,
        "converged": False,
    }
