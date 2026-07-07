"""Trajectory-DAG scorer for Family 3 (orchestrators / non-linear subagents).

Outcome alone doesn't evaluate an orchestrator: a right answer reached by
firing nine redundant subagents is a failure of the very thing under test. So
we score the **process** — the DAG of subagent invocations the orchestrator
actually produced — against a reference DAG, deterministically (no LLM):

* node F1 — did it call the right subagents (precision guards against
  fan-out waste, recall against missing steps)?
* edge F1 — did it respect the right dependencies (run detection *after*
  fetching, not before)?
* frugality — did it stay within the call budget? Orchestrators are where
  cost explodes; frugality is a first-class scored dimension, not a footnote.

A malformed trajectory (unparseable, a dependency on an unknown step, or a
cycle) scores 0 — an orchestrator that emits an invalid plan has failed.

The trajectory is a JSON object the solver emits (in a real run, captured from
the tool-call trace)::

    {"calls": [{"id": "s1", "agent": "fetch_waveform", "deps": []},
               {"id": "s2", "agent": "detect",        "deps": ["s1"]}],
     "answer": "..."}

Process score combines multiplicatively with any outcome scorer downstream
(see docs/orchestration_scorer.md); this module returns the process score.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

_DEFAULT_WEIGHTS = {"nodes": 0.4, "edges": 0.4, "frugality": 0.2}


def _set_f1(observed: set, expected: set) -> float:
    """F1 over two sets. Empty-vs-empty == 1.0 (correctly did nothing)."""
    if not observed and not expected:
        return 1.0
    tp = len(observed & expected)
    precision = tp / len(observed) if observed else 0.0
    recall = tp / len(expected) if expected else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _parse_trajectory(model_output: str) -> dict | None:
    """Extract the trajectory JSON object from a model response."""
    depth = 0
    start = None
    for i, ch in enumerate(model_output):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(model_output[start : i + 1])
                except json.JSONDecodeError:
                    start = None
                    continue
                if isinstance(obj, dict) and "calls" in obj:
                    return obj
                start = None
    return None


def _is_acyclic(nodes: set[str], edges: set[tuple[str, str]]) -> bool:
    """Kahn's algorithm on id-level edges; True if the graph is a DAG."""
    indeg = dict.fromkeys(nodes, 0)
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        adj[a].append(b)
        indeg[b] += 1
    queue = [n for n in nodes if indeg[n] == 0]
    seen = 0
    while queue:
        n = queue.pop()
        seen += 1
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    return seen == len(nodes)


def make_trajectory_dag_scorer(
    *,
    expected_agents: list[str],
    expected_edges: list[list[str]] | None = None,
    max_calls: int | None = None,
    stage_weights: dict[str, float] | None = None,
) -> Callable[[str, Any], float]:
    """Score an orchestration trajectory against a reference DAG.

    * ``expected_agents`` — subagents the reference plan invokes (by name).
    * ``expected_edges`` — reference dependency edges as ``[from, to]`` agent
      names (a dependency: ``to`` must run after ``from``).
    * ``max_calls`` — call budget; exceeding it decays the frugality stage.
    """
    exp_agents = set(expected_agents)
    exp_edges = {(a, b) for a, b in (expected_edges or [])}
    weights = {**_DEFAULT_WEIGHTS, **(stage_weights or {})}

    def scorer(model_output: str, gold: Any) -> float:
        traj = _parse_trajectory(model_output)
        if traj is None:
            return 0.0
        calls = traj.get("calls")
        if not isinstance(calls, list):
            return 0.0

        id_to_agent: dict[str, str] = {}
        for c in calls:
            if not isinstance(c, dict) or "id" not in c or "agent" not in c:
                return 0.0
            id_to_agent[str(c["id"])] = str(c["agent"])

        # id-level edges from deps; every dep must reference a known step.
        id_edges: set[tuple[str, str]] = set()
        agent_edges: set[tuple[str, str]] = set()
        for c in calls:
            cid = str(c["id"])
            for dep in c.get("deps", []) or []:
                dep = str(dep)
                if dep not in id_to_agent:
                    return 0.0  # dangling dependency -> invalid plan
                id_edges.add((dep, cid))
                agent_edges.add((id_to_agent[dep], id_to_agent[cid]))

        if not _is_acyclic(set(id_to_agent), id_edges):
            return 0.0  # a cyclic plan cannot execute

        node_f1 = _set_f1(set(id_to_agent.values()), exp_agents)
        edge_f1 = _set_f1(agent_edges, exp_edges) if exp_edges else 1.0

        n = len(calls)
        if max_calls is None or n <= max_calls:
            frugality = 1.0
        else:
            frugality = max_calls / n if n else 1.0

        score = (
            weights["nodes"] * node_f1
            + weights["edges"] * edge_f1
            + weights["frugality"] * frugality
        )
        return max(0.0, min(1.0, score))

    return scorer


def make_scorer_from_spec(spec: dict[str, Any]) -> Callable[[str, Any], float]:
    """Reconstruct a Family-3 scorer callable from a JSON-serializable spec.

    Recognised names: ``trajectory_dag``, ``zero``.
    """
    name = spec["name"]
    config = dict(spec.get("config", {}))
    if name == "trajectory_dag":
        return make_trajectory_dag_scorer(
            expected_agents=config["expected_agents"],
            expected_edges=config.get("expected_edges"),
            max_calls=config.get("max_calls"),
            stage_weights=config.get("stage_weights"),
        )
    if name == "zero":
        return lambda _out, _gold: 0.0
    raise ValueError(f"unknown scorer name: {name!r}")
