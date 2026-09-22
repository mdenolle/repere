# Numerical-regression scoring (Family 2: coding agents, data-out)

Status: proposed (Phase 4 candidate). Reference implementation lives in
`src/repere_suites/pipeline_regression/`.

## Why

Repère's coding-agent tasks come in two shapes:

1. **prompt → code, scored by execution** — the model writes a script; we run it
   and check it produced the right artifact. Covered today by
   `code_execution` (staged 4×0.25) and `plot_ssim`.
2. **prompt → data, scored by regression** — the model drives a real scientific
   pipeline (seisbench phase picking, noisepy ambient-noise cross-correlation,
   codameter coda measurements) and produces a *numeric* output. Correctness is
   "is the number right, within tolerance?", not "does a file exist?".

Shape (2) has no scorer today. This doc specifies `numerical_regression`, the
tier-T1 scorer that closes the gap.

## Where it sits on the scorability spectrum

| Tier | Gold | Scorer | Judge noise |
|------|------|--------|-------------|
| T0 deterministic | exact/structured value | field match + tolerance | none |
| **T1 numerical** | **reference array/scalar** | **`numerical_regression`** | **none** |
| T2 perceptual | reference artifact | `plot_ssim` | low |
| T3 trajectory | reference process/DAG | tool-set P/R, graph edit dist | low–med |
| T4 rubric | criteria, no single gold | pinned-rubric LLM-judge | high |

Verifiable-core discipline: the *scientific* answer (pick time, correlation
coefficient, coda Q) is compared to a reference with a **numeric tolerance and
no LLM in the loop**, so the leaderboard signal is cheap and trustworthy.

## Contract

The model's code runs in the existing sandbox (`sandbox.run_snippet`) and reports
its numeric output through the standard `record(**kwargs)` capture helper:

```python
# model-generated snippet, run in the pinned sandbox
picks = phasenet_pick(stream)              # the real pipeline
record(p_picks=[t.timestamp for t in picks])   # numeric output captured as JSON
```

The scorer pulls `artifacts["p_picks"]` and compares it to the item's `gold`
(the reference array), using one of the metrics below. `gold` travels as the
runtime second argument to the scorer — same convention as `json_extraction`.

## Scoring composition

Staged, mirroring `code_execution`, but with the final stage **graded** rather
than binary — because for a regression task the number *is* the point:

| stage | default weight | passes when |
|-------|----------------|-------------|
| `code` | 0.10 | a code block was extracted |
| `calls` | 0.10 | all `required_calls` substrings present (auto-pass if none) |
| `runs` | 0.10 | snippet ran `ok` **and** `artifact_key` was recorded |
| `accuracy` | 0.70 | `metric(got, gold)` ∈ [0,1], multiplied by the weight |

Weights are configurable via `stage_weights`; they sum to 1.0. The heavy
accuracy weight is the verifiable-core stance — a pipeline that runs but returns
wrong numbers scores ≤ 0.30, well below one that runs and is correct.

## Metrics

Pure-Python (no numpy dependency in the scorer path, matching the
optional-`scikit-image` caution in `plot_ssim`):

- **`pick_f1`** — `got`/`gold` are lists of event times (seconds). Greedy
  match within `tolerance` s; score = F1 of matched picks. The seisbench
  reference metric. Handles empty predictions/gold.
- **`allclose`** — elementwise fraction of entries within `(rtol, atol)`;
  flattens nested lists; shape mismatch → 0.
- **`pearson`** — `max(0, r)` of flattened `got` vs `gold`. Waveform-shape
  metric for noisepy CCFs (a shifted-but-correlated CCF still scores high).
- **`rmse`** — `max(0, 1 − rmse / rmse_scale)`; requires `rmse_scale`.

## Serialisable spec

Registered in the suite's `make_scorer_from_spec` so `items()` and
`export_rows()` share one source of truth and the row is shippable to HF:

```json
{"name": "numerical_regression",
 "config": {"artifact_key": "p_picks", "metric": "pick_f1",
            "tolerance": 0.5, "required_calls": ["record("]}}
```

## Infra note — per-suite sandbox images (wired)

P2.2 pins **one** image for every task. seisbench pulls torch; noisepy is heavy.
A single mega-image is slow and brittle. So each regression pipeline names its
own image via a `sandbox_image` field in `pipelines.yaml`, which flows into the
serialisable `scorer_spec` and is passed to `run_snippet(..., image=...)`. The
resolution order in the docker backend is: explicit `image` arg → `FM_SANDBOX_IMAGE`
→ `DEFAULT_SANDBOX_IMAGE`. The host backend ignores it. Cheap tasks keep the light
`ghcr.io/mdenolle/repere-sandbox`; only the ML suites pay for the fat image.

Still to do: publish the per-suite images
(`repere-sandbox-seisbench`, `repere-sandbox-noisepy`) and add a CI job
that builds them, mirroring `.github/workflows/sandbox-image.yml`.

## Follow-ups (not in this reference)

- Promote shared scorers to `src/repere/scorers.py` so seisbench, noisepy,
  and codameter suites import one factory instead of copying it.
- Grow `pipelines.yaml` into a parametric truth set (à la `events.yaml`) with
  `split`/`visibility`/`cutoff_date` and negative cases (a pipeline that should
  return *no* picks — the regression analogue of `expected_detection: false`).
