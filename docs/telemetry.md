# Repère telemetry — JSONL log schema

Repère writes evaluation telemetry as append-only JSON Lines under
`results/*.jsonl`. The schema is versioned (current: **v2**, shipped in
P2.5) and the field names align with InspectAI's `EvalSample` /
`EvalOutput` so the data shape maps cleanly to Inspect's `.eval` log
format without per-record glue.

## Why JSONL (and not Inspect's `.eval`)

Inspect's native log format is a zipped JSON archive. We deliberately
keep JSONL because:

- **Streaming.** A long run can be `tail -f`'d and parsed line-by-line
  by external tooling without reading the whole file.
- **Crash recovery.** Every line is flushed individually, so a SIGKILL
  leaves a recoverable log.
- **Diff-friendliness.** Plain JSON survives `git diff` and code review
  inspection; zipped formats don't.

What P2.5 buys is **field-level alignment**: a future converter can
turn a Repère JSONL log into an Inspect `.eval` archive with a
shallow rename map, because the per-sample fields already match.

## v2 record shapes

Every record carries `schema_version: 2`, an ISO-8601 `ts`, and a
`run_id` (UUID4) that links it back to the enclosing run. Type-specific
fields:

### `run_start` — one per `with JSONLTelemetry(...)` block

```json
{
  "type": "run_start",
  "schema_version": 2,
  "ts": "2026-05-11T14:30:00Z",
  "run_id": "8f6a1c…",
  "created": "2026-05-11T14:30:00Z",
  "metadata": { "...caller-provided dict..." },
  "task": "sta_lta.intent_extraction",
  "task_args": { "split": "validation" },
  "solver": "generate",
  "model": "anthropic/claude-haiku-4-5"
}
```

`task`, `task_args`, `solver`, and `model` are emitted only when the
caller passes them — null attribution would be misleading.

### `sample` — one per scored generation

```json
{
  "type": "sample",
  "schema_version": 2,
  "ts": "2026-05-11T14:30:01Z",
  "run_id": "8f6a1c…",
  "id": "sta_lta.intent_extraction:0",
  "epoch": 0,
  "suite": "sta_lta.intent_extraction",
  "score": 0.87,
  "output": {
    "text": "...model completion...",
    "model_id": "anthropic/claude-haiku-4-5",
    "prompt_tokens": 412,
    "output_tokens": 38,
    "latency_s": 1.21,
    "cost_usd": 0.0019
  },
  "skill_name": "stalta-detection",
  "skill_mode": "full"
}
```

`id` is auto-derived from `f"{suite}:{epoch}"` when not passed
explicitly. `output` holds the dict / dataclass returned by the
adapter (typically a `Generation`).

### `run_end` — closes the run

```json
{
  "type": "run_end",
  "schema_version": 2,
  "ts": "2026-05-11T14:30:42Z",
  "run_id": "8f6a1c…",
  "completed": "2026-05-11T14:30:42Z",
  "ok": true
}
```

### Custom events — `log_event(name, payload)`

```json
{
  "type": "budget_skip",
  "schema_version": 2,
  "ts": "2026-05-11T14:30:05Z",
  "run_id": "8f6a1c…",
  "payload": { "model_id": "...", "estimate_usd": 0.04 }
}
```

## Field mapping — Repère ↔ Inspect `EvalSample` / `EvalOutput`

| Repère v2 field        | Inspect equivalent          | Notes |
| -------------------------- | --------------------------- | ----- |
| `run_id`                   | `EvalLog.run_id`            | UUID4 generated at run start. |
| `created`, `completed`     | `EvalLog.created`, `.completed` | ISO-8601 UTC. |
| `task`                     | `EvalLog.task`              | E.g. `sta_lta.intent_extraction`. |
| `task_args`                | `EvalLog.task_args`         | Dict of solver-visible task knobs. |
| `solver`                   | `EvalLog.solver`            | `"generate"`, `"stalta_react"`, etc. |
| `model`                    | `EvalLog.model`             | Adapter/provider/model id. |
| `id` (per-sample)          | `EvalSample.id`             | `f"{suite}:{epoch}"` by default. |
| `epoch`                    | `EvalSample.epoch`          | Was `item_index` in v1. |
| `output`                   | `EvalSample.output`         | Was `generation` in v1. |
| `output.text`              | `EvalOutput.choices[0].message.content` | Single-choice case. |
| `output.prompt_tokens`     | `EvalOutput.usage.input_tokens`         | |
| `output.output_tokens`     | `EvalOutput.usage.output_tokens`        | |
| `output.cost_usd`          | (no direct field; tracked separately in `EvalLog.stats`) | Repère-native; preserved. |
| `score`                    | `EvalSample.score.value`    | Float in [0, 1] for our scorers. |
| `suite`, `skill_name`, `skill_mode` | (no Inspect analog) | Repère-specific, preserved. |

Fields without an Inspect analog (`suite`, `skill_name`, `skill_mode`,
`cost_usd`) are kept under their Repère names rather than forced
into an unrelated Inspect field — the goal is *cleanest mapping*, not
maximum field reuse.

## Read path

Use `repere.telemetry.read_jsonl(path)` to load a log into memory.
By default v1 records are silently normalised to v2 shape so downstream
code only ever handles one schema. Pass `normalise=False` to inspect
raw on-disk bytes (useful for schema-drift detection or wire-format
assertions).

```python
from repere.telemetry import read_jsonl

records = read_jsonl("results/run.jsonl")
samples = [r for r in records if r["type"] == "sample"]
```

## v1 → v2 read-time normalisation (compat shim)

v1 logs (Repère ≤ 0.3.0) had no `schema_version` field. The shim
applies these rewrites in memory; **no on-disk migration is performed**:

| v1                            | v2                          |
| ----------------------------- | --------------------------- |
| `type: "generation"`          | `type: "sample"`            |
| `generation: {...}`           | `output: {...}`             |
| `item_index: 7`               | `epoch: 7`                  |
| (no `id`)                     | `id: f"{suite}:{epoch}"` when both are known; `f"sample:{epoch}"` otherwise; absent if epoch is also missing |
| (no `schema_version`)         | `schema_version: 1`         |

`run_start` and `run_end` records pre-date `run_id` and are left
alone except for the `schema_version: 1` marker. v1 sample records
also don't carry a `run_id`, so callers that key off `run_id` should
guard for its absence on migrated records.

## Versioning policy

A change that adds an optional field is **minor** (no version bump).
A rename or removal is **major** (bump `TELEMETRY_SCHEMA_VERSION` and
add a new branch to `_normalise_v1_to_v2`-style shim). The shim must
keep reading every previously-shipped version for at least one minor
release after the bump.
