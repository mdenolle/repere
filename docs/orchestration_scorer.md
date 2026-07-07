# Orchestration scoring (Family 3: non-linear subagent workflows)

Status: proposed (Phase 4 candidate). Reference implementation:
`src/frugalmind_suites/orchestration/`.

## Why this is the hard one

Families 1–2 have a single solver produce one artifact. An orchestrator is
different: it decides **which subagents to call, in what order, with what
dependencies** — a DAG, not a chain. Two things follow:

1. **Outcome alone is not a sufficient signal.** A correct answer reached by
   firing nine redundant subagents is a failure of the thing under test. You
   must score the *process*, not just the result.
2. **The existing agent layer (`basic_agent` ReAct loop) is linear.** Real
   Family-3 evaluation needs a subagents-as-tools solver (below).

## What the scorer measures — `trajectory_dag`

Deterministic, no LLM. The orchestrator emits (or, in a real run, we capture) a
trajectory:

```json
{"calls": [{"id": "s1", "agent": "fetch_waveform", "deps": []},
           {"id": "s2", "agent": "fetch_waveform", "deps": []},
           {"id": "s3", "agent": "detect", "deps": ["s1"]},
           {"id": "s4", "agent": "detect", "deps": ["s2"]},
           {"id": "s5", "agent": "locate", "deps": ["s3", "s4"]},
           {"id": "s6", "agent": "draft_report", "deps": ["s5"]}],
 "answer": "..."}
```

Scored against a reference DAG (`expected_agents`, `expected_edges` by agent
name):

| stage | weight | measures |
|-------|--------|----------|
| node F1 | 0.4 | right subagents called — precision penalises fan-out waste, recall penalises missing steps |
| edge F1 | 0.4 | right dependencies respected — e.g. `locate` fans in from *both* detections |
| frugality | 0.2 | stayed within `max_calls` — decays as `max_calls / n` past budget |

**Hard-fail to 0** (an invalid plan is not partially correct): unparseable
trajectory, a dependency on an unknown step id, or a cycle (checked via Kahn's
algorithm — a cyclic plan cannot execute).

## Frugality is first-class here

Orchestrators are where cost explodes via fan-out, so frugality is a scored
dimension, not framing — this is the FrugalMind differentiator AstaBench's
orchestration evals lack. Combine with `BudgetGuard`/`FrugalRouter` and the
cost-vs-quality Pareto chart: the interesting question for Family 3 is not "did
it succeed" but "did it succeed *cheaply*".

## Combining with outcome

`trajectory_dag` returns the **process** score. For end-to-end grading, combine
multiplicatively with an outcome scorer (the answer's correctness via any
Family 1/2 scorer): `final = outcome * process`. Multiplicative, not additive,
so a perfect answer with a garbage plan still scores low — which is the point.

## Substrate change needed — subagents-as-tools solver

The reference uses `generate()` (the model writes the plan as JSON), which
tests the scorer and lets a model be graded on *planning*. To evaluate real
orchestration you need a solver that exposes each `available_agent` as a
callable tool and records the invocation graph from the actual tool-call trace.
Sketch:

- Wrap each subagent as an `@tool` whose call is logged with a fresh `id` and
  the ids it consumed as `deps` (data dependency = which prior outputs it read).
- Run under an agent loop that permits fan-out (call two `fetch_waveform` tools
  before any `detect`), unlike the strictly-sequential `basic_agent`.
- Emit the captured graph in the trajectory shape above; feed to `trajectory_dag`.

This is the one genuine new solver in the three families. The GAIA stub's
`trajectory_quality` (LLM-judge over the trace) and `tool_efficiency` (Jaccard
of tools) are the seed; `trajectory_dag` generalises Jaccard-on-tools to
graph-structure-on-DAG.

## Follow-ups

- Graph-edit-distance variant for partial-credit on near-miss edge sets.
- Replanning credit: reward recovering after a subagent failure (needs the
  trace to record failures), penalise redundant retry storms.
- Grow `tasks.yaml` with negative cases (a goal where the correct plan is a
  *single* call — over-orchestration is the failure to catch).
