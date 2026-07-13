# Annotating a paper for the research-workflow eval ("agentify the paper")

This is the guide for adding one of your papers to the Family-3 evaluation. It
takes about **20 minutes per paper** and it is the one eval in FrugalMind that
**only a working research group can build** — because the ground truth is *what
you actually did*, and nobody else knows it.

## What the eval asks

Given a paper, an orchestrator must emit the **research workflow** that produces
it: a DAG of research operations and their dependencies. It is graded on the
graph — did it call for the right operations (node F1), get the dependencies
right (edge F1), and refrain from inventing methodology the paper never performed
(frugality/precision)? No LLM judge is involved anywhere.

## Why the vocabulary is closed

You annotate using the fixed operation list in
[`ontology.yaml`](../src/frugalmind_suites/paper_workflow/ontology.yaml).

A free-text plan cannot be scored: *"compute the correlations"* and
*"cross-correlate the noise"* are the same step written two ways, and no metric
can see that. Constraining the plan to a fixed alphabet turns an essay into a
graph, and a graph can be compared deterministically.

The cost is expressiveness. If your paper genuinely needs a step that is not in
the list, **extend the ontology deliberately** (add the term, bump its version,
say why) rather than inventing a term in your annotation — the validator will
reject an unknown term, because a term the model is never shown can never be
matched.

## The contamination rule — this is the important part

**Published papers are in the models' training data.** A model may be reciting
your methods section rather than reasoning about it. So:

| Your paper is… | split | visibility | Lives where | What it measures |
|---|---|---|---|---|
| **Published** | `validation` | `public` | in the repo | development only — **not** a trustworthy capability measurement |
| **Unpublished / in preparation** | `test` | `private` | gated dataset, **never git** | **planning, not recall** — the only honest number |

Your in-progress papers are in no training corpus. That makes them uniquely
valuable: they are the only way to know whether a model can *design* a research
workflow rather than *remember* one. This is the same principle as the
secret-seed hidden split, applied to literature (see
[`dataset_submission.md`](dataset_submission.md)).

Set `cutoff_date` to the paper's public appearance date, so a retrieval-augmented
agent cannot simply look the answer up.

> **Unpublished annotations must never be committed.** Put them in
> `data/private/paper_workflow_test.yaml` (gitignored) and upload to the gated
> dataset.

## Difficulty tiers

The model is given progressively less to work with. Set `tier:` accordingly.

| tier | The model sees | What it tests |
|---|---|---|
| `easy` | title + abstract + methods | extraction |
| `medium` | title + abstract | inferring the methodology |
| `hard` | **title only** | **designing** the workflow — genuine research reasoning |

The `hard` tier is the interesting one. Prefer it where the title alone states a
well-posed research question.

## How to annotate

1. **List the operations you actually ran.** Not the ones a reader might imagine
   — the ones that happened. If you never ran a simulation, `forward_model` is
   *not* in your workflow, and a model that adds it should lose points.
2. **Write the dependencies.** `[a, b]` means *b depends on a* (b runs after a).
   Capture the real data dependencies, including fan-in (a validation step that
   needs both your measurement *and* the catalogue).
3. **Set `max_calls`** — the frugality budget. A reasonable default is
   `len(nodes) + 3`. This is what penalises an orchestrator that pads the plan.
4. **Run the validator.** It checks the ontology, the edges, acyclicity, the
   physical-ordering invariants, and that your reference workflow scores 1.0
   against its own gold:

   ```bash
   pixi run -e full python scripts/validate_paper_workflows.py
   ```

## Template

```yaml
  - id: your-paper-short-id
    tier: medium              # easy | medium | hard
    split: validation         # `test` for UNPUBLISHED work (and keep it out of git)
    visibility: public        # `private` for `test`
    cutoff_date: "2025-06-01"
    title: >-
      The paper's title.
    abstract: >-
      The paper's abstract.
    # methods: >-             # only needed for tier: easy
    #   The methods section.
    workflow:
      nodes:
        - acquire_waveforms
        - preprocess_waveforms
        - compute_correlation
        - measure_dvv
        - visualize
        - interpret
      edges:
        - [acquire_waveforms, preprocess_waveforms]
        - [preprocess_waveforms, compute_correlation]
        - [compute_correlation, measure_dvv]
        - [measure_dvv, visualize]
        - [visualize, interpret]
      max_calls: 9
```

## What is deliberately *not* scored

- **Prose quality** of the plan. We score the graph.
- **Parameter choices** (which filter band, which estimator). That is the
  software-agent family's job (see the dv/v eval); here we ask only *which
  operations, in what order*.
- **Whether the workflow is the "best" one.** It is scored against *your* actual
  workflow, not against an ideal. If two workflows are both defensible, that is a
  limitation of the reference-DAG approach and should be recorded in the paper —
  the honest fix is multiple accepted references per paper, which the scorer does
  not yet support.

## Current status

The two entries in `papers.yaml` are **provisional worked examples**, annotated
from public abstracts by the framework author to exercise the schema. They are
marked `provisional: true` and the validator warns about them. **They must be
validated or replaced by a domain author before any published number.**
