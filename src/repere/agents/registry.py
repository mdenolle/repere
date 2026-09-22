"""Tool registry for Repère agentic evals.

This is the single extension point for **attaching tools to models**. A tool
is any InspectAI ``@tool`` factory (a zero-arg callable returning a ``Tool``).
Registering it here gives it a stable *name* that suites and solvers reference
without importing the tool module directly, so:

* a new suite can request its tools by name and get a fresh bundle, and
* the same tool surface is guaranteed identical across every model (Gemma,
  Qwen, Claude, …) — which is what makes the open-vs-frontier comparison fair.

Adding a tool is three lines (see ``docs/agentic_eval.md``)::

    from inspect_ai.tool import Tool, tool
    from repere.agents.registry import register_tool

    @register_tool("my_tool", "One-line description for prompts and docs.")
    @tool
    def my_tool() -> Tool:
        async def execute(x: str) -> str:
            ...
        return execute

``inspect_ai`` is imported lazily inside the tool bodies, but registering a
tool only stores the *factory* — the registry itself has no hard dependency on
the eval extra until you actually call :func:`resolve_tools`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from inspect_ai.tool import Tool

# A tool factory is a zero-arg callable that returns a fresh Inspect ``Tool``.
ToolFactory = Callable[[], "Tool"]


@dataclass(frozen=True)
class ToolSpec:
    """Static description of a registered tool.

    Attributes
    ----------
    name:
        Stable identifier suites and solvers use to request the tool.
    factory:
        Zero-arg callable returning a fresh Inspect ``Tool`` instance. Called
        once per solver construction so no tool state leaks across samples.
    description:
        One-line human summary. Surfaced in ``tools_dict()`` (docs, tests) and
        handy for building system prompts that enumerate the tool surface.
    requires:
        Optional tuple of extra names the tool needs at *call* time (e.g.
        ``("geo",)`` for ObsPy). Purely advisory metadata — the registry does
        not enforce it, but a runner can warn before spending budget.
    """

    name: str
    factory: ToolFactory
    description: str
    requires: tuple[str, ...] = ()


_REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    """Register a :class:`ToolSpec`. Raises on a duplicate name."""
    if spec.name in _REGISTRY:
        raise ValueError(f"tool {spec.name!r} is already registered; names must be unique")
    _REGISTRY[spec.name] = spec
    return spec


def register_tool(
    name: str,
    description: str,
    *,
    requires: tuple[str, ...] = (),
) -> Callable[[ToolFactory], ToolFactory]:
    """Decorator form of :func:`register`.

    Wraps a tool *factory* (the ``@tool``-decorated function) and returns it
    unchanged, so it can still be imported and called directly.
    """

    def _decorate(factory: ToolFactory) -> ToolFactory:
        register(ToolSpec(name=name, factory=factory, description=description, requires=requires))
        return factory

    return _decorate


def get_spec(name: str) -> ToolSpec:
    """Return the :class:`ToolSpec` for ``name`` or raise ``KeyError``."""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        available = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(f"unknown tool {name!r}; registered tools are: {available}") from exc


def resolve_tools(names: list[str]) -> list[Tool]:
    """Instantiate a fresh tool bundle for the given names, preserving order.

    Each name is resolved via :func:`get_spec` and its factory called once.
    This is what a solver hands to Inspect's ``basic_agent(tools=...)``.
    """
    return [get_spec(name).factory() for name in names]


def list_tools() -> list[str]:
    """Registered tool names, sorted for stable diffs and docs."""
    return sorted(_REGISTRY)


def tools_dict() -> dict[str, str]:
    """Mapping of ``name -> description`` for every registered tool.

    Import-light view of the tool surface for tests, docs, and prompt
    construction — does not instantiate any tool.
    """
    return {name: spec.description for name, spec in sorted(_REGISTRY.items())}


# ---------------------------------------------------------------------------
# Default bundles. A "toolset" is just an ordered name list; a suite requests
# one when it builds its solver.
# ---------------------------------------------------------------------------

STALTA_TOOLSET: tuple[str, ...] = (
    "fdsn_get_waveforms",
    "python_session",
    "record_submit",
)

# RAG over a frozen scientific corpus: retrieve then submit a ranked list.
LIT_RAG_TOOLSET: tuple[str, ...] = (
    "literature_search",
    "record_submit",
)


def _lazy_factory(module: str, attr: str) -> ToolFactory:
    """Build a factory that imports ``module`` only when called, so
    registering a built-in tool doesn't drag ``inspect_ai`` into an
    import-light context (docs, ``tools_dict()``, tests)."""

    def factory() -> Tool:
        import importlib

        mod = importlib.import_module(module)
        return getattr(mod, attr)()

    return factory


def _register_builtin_tools() -> None:
    """Idempotently register the built-in tools.

    Called at import (below) and again defensively from the solvers; the name
    guard makes repeat calls safe. Descriptions are stored eagerly; the tool
    objects are only built when a solver resolves them, so this needs no
    ``[eval]`` extra.
    """
    _builtins = (
        ToolSpec(
            "fdsn_get_waveforms",
            _lazy_factory("repere.agents.tools", "fdsn_get_waveforms"),
            "ObsPy FDSN waveform fetch (network, station, channel, time window)",
            requires=("geo",),
        ),
        ToolSpec(
            "python_session",
            _lazy_factory("repere.agents.tools", "python_session"),
            "Run a Python snippet in the STA/LTA subprocess sandbox",
        ),
        ToolSpec(
            "record_submit",
            _lazy_factory("repere.agents.tools", "record_submit"),
            "Submit the final answer for scoring",
        ),
        ToolSpec(
            "literature_search",
            _lazy_factory("repere.agents.lit_tools", "literature_search"),
            "Search a frozen scientific corpus; returns ranked papers with stable ids",
        ),
    )
    for spec in _builtins:
        if spec.name not in _REGISTRY:
            register(spec)


_register_builtin_tools()


__all__ = [
    "ToolSpec",
    "ToolFactory",
    "STALTA_TOOLSET",
    "LIT_RAG_TOOLSET",
    "register",
    "register_tool",
    "get_spec",
    "resolve_tools",
    "list_tools",
    "tools_dict",
]
