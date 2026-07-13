---
name: research-orchestration
version: v0.1
task_kind: orchestration
description: >-
  Domain skill for decomposing a geophysics paper into the research workflow that
  produces it. Use when an orchestrator must plan which research operations to
  run and in what order. Teaches the two failure modes that dominate: inventing
  methodology the paper never performed, and getting the data dependencies wrong.
validators:
  - "uses_only_ontology_operations"
  - "no_invented_methodology"
---

# Planning a research workflow from a paper

You are producing the **plan a group would actually execute**, not a summary of
the paper. Two failure modes dominate, and both are penalised.

## 1. Do not invent methodology

The single most common error is padding the plan with operations that sound like
good science but that this paper never performed. A paper that measures dv/v from
ambient noise did **not** necessarily run a simulation, invert for structure, or
train a model. Adding `forward_model`, `invert` or `train_ml_model` because they
seem sophisticated **costs precision**, and precision is scored.

Rule: an operation belongs in the plan **only if the paper's own text implies it
was carried out**. If the abstract does not support it, leave it out. A short,
correct plan beats a long, impressive one.

## 2. Dependencies are data dependencies

An edge `a -> b` means *b consumes what a produces*. Do not encode narrative
order ("they discussed X before Y"); encode **what must exist before what can
run**.

The physically obligatory ones:

- You cannot `preprocess_waveforms` before `acquire_waveforms`.
- `measure_dvv` runs on correlation functions -> it depends on
  `compute_correlation` (usually via `stack`), never on raw records.
- `locate_events` consumes picks -> it depends on `pick_phases`.
- `invert` consumes conditioned data -> it depends on `preprocess_waveforms`.
- Response removal needs the instrument response -> `preprocess_waveforms`
  depends on `acquire_metadata` whenever the paper works in physical units.

## 3. Fan-in is where plans go wrong

Validation and interpretation almost always **fan in** from more than one branch.
A step that compares your measurement against a catalogue depends on **both** the
measurement *and* `acquire_catalog` — two incoming edges, not one. Orchestrators
routinely emit a single chain and lose every fan-in edge.

Look for these fan-ins:
- `validate_against_reference` <- (your measurement) + (the independent source)
- `interpret` <- (the result) + (the validation)
- `compute_correlation` <- (station A data) + (station B data), when pairwise

## 4. The shape of a typical observational workflow

```
acquire_* ──► preprocess_waveforms ──► quality_control ──► <measurement>
                     ▲                                          │
              acquire_metadata                                  ▼
                                            acquire_catalog ─► validate_against_reference
                                                                │
                                                                ▼
                                                    visualize ─► interpret
```

Not every paper has every step. Delete, do not decorate.

## 5. Output contract

Emit **only** the JSON object. Each call has an `id`, an `agent` (an operation
name taken verbatim from the vocabulary you were given), and `deps` (the ids it
depends on):

```json
{"calls": [
  {"id": "s1", "agent": "acquire_waveforms", "deps": []},
  {"id": "s2", "agent": "preprocess_waveforms", "deps": ["s1"]}
]}
```

An operation name not in the vocabulary cannot be scored and is simply lost. No
prose, no code fence, no commentary.
