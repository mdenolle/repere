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
            cid = str(c["id"])
            if cid in id_to_agent:
                return 0.0  # duplicate step id -> invalid plan
            id_to_agent[cid] = str(c["agent"])

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


# ---------------------------------------------------------------------------
# Dynamic workflows — trajectory_policy
#
# A static reference DAG cannot score a workflow whose correct shape depends on
# what the agent observes at runtime (low SNR -> re-fetch; no detections ->
# stop; transient failure -> recover). trajectory_policy instead checks
# deterministic conditional invariants over a *recorded trace* whose calls
# carry the observation each step returned:
#
#   {"calls": [{"id": "s1", "agent": "fetch_waveform",
#               "args": {"station": "NC.JBGB"}, "deps": [], "obs": {"snr": 2.1}},
#              ...]}
#
# This is the invariant layer of the dynamic-eval design (see
# docs/orchestration_scorer.md). The scenario harness that *produces* such
# traces deterministically, and the cross-scenario branch-sensitivity metric,
# are the follow-on layers.
# ---------------------------------------------------------------------------


def _obs_match(obs: Any, comp: dict | None) -> bool:
    """Evaluate a serialisable comparator against a call's observation dict.

    ``comp`` is ``{"field": ..., "op": ..., "value": ...}`` with ``op`` in
    ``==`` ``!=`` ``<`` ``<=`` ``>`` ``>=`` ``truthy`` ``falsy``. A missing
    field or a type-incompatible comparison is a non-match, never an error.
    """
    if comp is None:
        return True
    if not isinstance(obs, dict):
        return False
    val = obs.get(comp["field"])
    op = comp["op"]
    if op == "truthy":
        return bool(val)
    if op == "falsy":
        return not bool(val)
    if val is None:
        return False
    target = comp.get("value")
    try:
        if op == "==":
            return val == target
        if op == "!=":
            return val != target
        if op == "<":
            return val < target
        if op == "<=":
            return val <= target
        if op == ">":
            return val > target
        if op == ">=":
            return val >= target
    except TypeError:
        return False
    raise ValueError(f"unknown comparator op: {op!r}")


def _validate_calls(calls: list) -> dict[str, str] | None:
    """Shape/DAG validation shared with trajectory_dag: unique ids, deps that
    resolve, acyclic. Returns id→agent, or None if the plan is invalid."""
    id_to_agent: dict[str, str] = {}
    for c in calls:
        if not isinstance(c, dict) or "id" not in c or "agent" not in c:
            return None
        cid = str(c["id"])
        if cid in id_to_agent:
            return None
        id_to_agent[cid] = str(c["agent"])
    id_edges: set[tuple[str, str]] = set()
    for c in calls:
        cid = str(c["id"])
        for dep in c.get("deps", []) or []:
            dep = str(dep)
            if dep not in id_to_agent:
                return None
            id_edges.add((dep, cid))
    if not _is_acyclic(set(id_to_agent), id_edges):
        return None
    return id_to_agent


def _rule_precondition(calls: list, rule: dict) -> bool:
    """Every call to ``agent`` must be preceded by ≥``min_count`` calls to
    ``requires_agent`` whose obs match ``requires_obs``."""
    agent = rule["agent"]
    req_agent = rule["requires_agent"]
    req_obs = rule.get("requires_obs")
    min_count = rule.get("min_count", 1)
    for i, c in enumerate(calls):
        if c["agent"] != agent:
            continue
        count = sum(
            1
            for j in range(i)
            if calls[j]["agent"] == req_agent and _obs_match(calls[j].get("obs"), req_obs)
        )
        if count < min_count:
            return False
    return True


def _rule_guard(calls: list, rule: dict) -> bool:
    """Once ``forbidden_when_agent`` observes ``forbidden_obs``, no ``agent``
    call may follow (e.g. never draft_report after locate saw no events)."""
    agent = rule["agent"]
    when_agent = rule["forbidden_when_agent"]
    when_obs = rule.get("forbidden_obs")
    for i, c in enumerate(calls):
        if c["agent"] == when_agent and _obs_match(c.get("obs"), when_obs):
            return not any(d["agent"] == agent for d in calls[i + 1 :])
    return True


def _rule_branch(calls: list, rule: dict) -> bool:
    """If ``when_agent`` observes ``when_obs``, a later ``then_agent`` call must
    exist — optionally with a different value for ``then_args_differ_field``
    (e.g. low SNR -> re-fetch from a *different* station)."""
    when_agent = rule["when_agent"]
    when_obs = rule.get("when_obs")
    then_agent = rule["then_agent"]
    differ = rule.get("then_args_differ_field")
    for i, c in enumerate(calls):
        if c["agent"] != when_agent or not _obs_match(c.get("obs"), when_obs):
            continue
        trigger_args = c.get("args") or {}
        ok = False
        for d in calls[i + 1 :]:
            if d["agent"] != then_agent:
                continue
            if differ is None:
                ok = True
                break
            if (d.get("args") or {}).get(differ) != trigger_args.get(differ):
                ok = True
                break
        if not ok:
            return False
    return True


def _rule_recovery(calls: list, rule: dict) -> bool:
    """After ``on_agent`` returns an error, require a corrective step and cap
    identical retries — the anti-retry-storm invariant."""
    on_agent = rule["on_agent"]
    error_field = rule.get("error_field", "error")
    then_agent = rule.get("then_agent")
    max_retries = rule.get("max_identical_retries", 1)
    err_comp = {"field": error_field, "op": "truthy"}
    for i, c in enumerate(calls):
        if c["agent"] != on_agent or not _obs_match(c.get("obs"), err_comp):
            continue
        after = calls[i + 1 :]
        identical = sum(
            1
            for d in after
            if d["agent"] == on_agent and (d.get("args") or {}) == (c.get("args") or {})
        )
        if identical > max_retries:
            return False
        if then_agent is not None and not any(d["agent"] == then_agent for d in after):
            return False
    return True


def _rule_termination(calls: list, rule: dict) -> bool:
    """A loop over ``agent`` must not exceed ``max_calls`` and must stop once it
    observes ``stop_when_obs`` (no further ``agent`` calls after the stop)."""
    agent = rule["agent"]
    max_calls = rule.get("max_calls")
    stop_obs = rule.get("stop_when_obs")
    agent_idx = [i for i, c in enumerate(calls) if c["agent"] == agent]
    if max_calls is not None and len(agent_idx) > max_calls:
        return False
    if stop_obs is not None:
        for k, idx in enumerate(agent_idx):
            if _obs_match(calls[idx].get("obs"), stop_obs):
                return k + 1 >= len(agent_idx)
    return True


_RULE_EVALUATORS: dict[str, Callable[[list, dict], bool]] = {
    "precondition": _rule_precondition,
    "guard": _rule_guard,
    "branch": _rule_branch,
    "recovery": _rule_recovery,
    "termination": _rule_termination,
}


def make_trajectory_policy_scorer(
    *,
    rules: list[dict],
    require_valid_dag: bool = True,
) -> Callable[[str, Any], float]:
    """Score a recorded dynamic-workflow trace against conditional invariants.

    Each rule in ``rules`` is a serialisable dict with a ``type`` in
    ``precondition`` / ``guard`` / ``branch`` / ``recovery`` / ``termination``.
    Score is the fraction of rules satisfied; an unparseable or (when
    ``require_valid_dag``) structurally-invalid trace hard-fails to 0.
    """
    for r in rules:
        if r.get("type") not in _RULE_EVALUATORS:
            raise ValueError(f"unknown policy rule type: {r.get('type')!r}")

    def scorer(model_output: str, gold: Any) -> float:
        traj = _parse_trajectory(model_output)
        if traj is None:
            return 0.0
        calls = traj.get("calls")
        if not isinstance(calls, list) or not calls:
            return 0.0
        for c in calls:
            if not isinstance(c, dict) or "id" not in c or "agent" not in c:
                return 0.0
        if require_valid_dag and _validate_calls(calls) is None:
            return 0.0
        if not rules:
            return 1.0
        passed = sum(1 for r in rules if _RULE_EVALUATORS[r["type"]](calls, r))
        return passed / len(rules)

    return scorer


def make_scorer_from_spec(spec: dict[str, Any]) -> Callable[[str, Any], float]:
    """Reconstruct a Family-3 scorer callable from a JSON-serializable spec.

    Recognised names: ``trajectory_dag``, ``trajectory_policy``, ``zero``.
    """
    name = spec["name"]
    config = dict(spec.get("config", {}))
    if name == "trajectory_policy":
        return make_trajectory_policy_scorer(
            rules=config["rules"],
            require_valid_dag=config.get("require_valid_dag", True),
        )
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
