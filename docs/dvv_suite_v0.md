# dv/v Processing Suite

A benchmark for choosing ambient-noise dv/v (relative seismic velocity change)
processing parameters, backed by the [codameter](https://github.com/Denolle-Lab/codameter)
synthetic engine. The ground truth is known exactly (seeded synthetic
cross-correlation functions with an imposed dv/v(t)), so every item is scored by
how well a choice recovers the truth, not by matching a fixed answer.

## What's in the box

| File | Purpose |
|---|---|
| `suite.py` | Two `DenolleGroupSuite` subclasses, one per output type. Thin adapter over `codameter.frugalmind`. |
| `scorers.py` | `make_scorer_from_spec` -> codameter's deterministic scorers. |

The cases (ten per suite) come from `codameter.golden.CASES`: six mainstream,
one per monitoring application (volcano, earthquake/fault, landslide,
groundwater, cryosphere, geothermal), on the `validation` split; and four edge
regimes (low SNR + large dv/v, clock drift + seasonal coda noise,
frequency-dependent shallow+deep media, sparse cadence + decorrelation) on
`test`.

## Two suites, two output types

| suite_id | task_kind | model returns | scorer | needs sandbox |
|---|---|---|---|---|
| `param_recommendation` | code_generation | a processing config (JSON) | `dvv_recovery`: run the config on the hidden synthetic, grade dv/v recovery | no |
| `dvv_series` | code_generation | the recovered dv/v(t) (JSON array) | `dvv_series_regression`: regress vs truth, null-anchored | yes (agent runs codameter) |

`param_recommendation` is the headline: it grades parameter judgment, is fully
deterministic, and needs no code execution. `dvv_series` is the end-to-end
stress test.

## Install and run

```bash
pip install -e ".[dvv]"      # pulls codameter (the scoring backend)

python - <<'PY'
import frugalmind as F
from frugalmind_suites.dvv import ALL_SUITES
reg = F.ModelRegistry()
runner = F.EvalRunner(registry=reg, suites=ALL_SUITES,
                      per_model_budget_usd=0.50, total_budget_usd=5.00)
PY
```

Export the frozen JSONL with the standard exporter (the dv/v suites are
registered in `frugalmind.cli._all_registered_suites()` whenever `codameter` is
importable):

```bash
frugalmind export-suite --suite dvv_processing.param_recommendation --out datasets/
# or, from codameter: pixi run frugalmind-export
```

## Scoring philosophy

Each scorer returns a value in `[0, 1]`. Negatives are first-class: a config
that picks the wrong depth band or an estimator that cycle-skips scores near
zero, and for the series task a no-change prediction scores ~0 by construction.
The `gold` payload carries only case identifiers (`case_id`, `use_case`) and
scalar tolerances, never the CCF arrays or the truth series, so the answer is not
embedded and the JSONL stays small. The scorer regenerates the synthetic from its
seed at scoring time.
