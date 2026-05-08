# STA/LTA Golden Suite

The first concrete `EvalSuite` for FrugalMind. Tests every step of the pipeline a small geophysics team would run on incoming seismic data: intent parsing → FDSN fetch → STA/LTA detection → plotting → reporting. Each step is graded independently against ground truth.

## What's in the box

| File | Purpose |
|---|---|
| `events.yaml` | Canonical truth set — 6 events spanning 4 categories (regional earthquake, teleseism, noise day, quarry blast). Add events here to extend the suite. |
| `items.py` | Five `EvalSuite` subclasses, one per `TaskKind` in the pipeline. Each emits one item per event. |
| `scorers.py` | Four scorer factories: JSON match, code execution, plot SSIM, catalog-claim regex. |
| `sandbox.py` | Subprocess-based code execution with timeout. Not a security boundary; it's a robustness boundary against runaway code. |
| `data/golden/` | Golden PNGs for SSIM scoring. Empty on first checkout — see "Generating goldens" below. |
| `test_suite.py` | Smoke tests for the deterministic parts (no ObsPy or network needed). |

## Suite × event matrix

Six events × five suites = 30 graded items in v0.1. Each event yields five test items automatically — adding a new event to `events.yaml` adds five new graded items across the pipeline.

## Running the suite

### Smoke tests

    pixi run test

These cover the deterministic scorers and the integration with `EvalRunner`. Pass before committing changes to suite logic.

### Full benchmark run

    import frugalmind as F
    from frugalmind_suites.sta_lta import ALL_SUITES

    F.load_env_keys()
    reg = F.ModelRegistry()
    runner = F.EvalRunner(
        registry=reg, suites=ALL_SUITES,
        per_model_budget_usd=0.50,
        total_budget_usd=5.00,
    )

The runner stops cleanly when a budget is hit and records partial results.

## Scoring philosophy

Each scorer returns a value in `[0.0, 1.0]`:

- **`make_json_extraction_scorer`** — field-level JSON matching with time tolerances.
- **`make_code_execution_scorer`** — staged code extraction, static-call, execution, and artifact credit.
- **`make_plot_ssim_scorer`** — PNG comparison to approved goldens using SSIM.
- **`make_report_scorer`** — report rubric with penalties for false positives.

## Negatives are first-class

The suite is deliberately not all-positive. A model that scores 1.0 on Nisqually but hallucinates an earthquake on a noise day is a worse model than one that scores 0.5 on Nisqually and correctly says "no events" on the noise day.

## Generating goldens

`STALTAPlotSuite` needs approved golden PNGs. Public sample goldens may live in `src/frugalmind_suites/sta_lta/data/golden/`. Private full-suite goldens should stay outside git and be passed with `FM_STALTA_GOLDEN_DIR`.

1. Run `STALTAPlotSuite` once with a trusted reference model and the actual ObsPy environment.
2. Manually inspect the output PNGs.
3. Copy approved outputs into the private or public golden location.
4. Commit only public sample artifacts.

This is intentionally a manual gate — golden generation should not be automatic, since a hallucinated trigger that gets enshrined as ground truth would silently corrupt the suite forever.

## What still needs doing

- Verify event metadata marked `VERIFY` against PNSN/ComCat before publishing numbers.
- Generate approved goldens for the public sample set and private full suite.
- Expand to ~15 events, including Cascadia ETS / tremor, volcano-hosted seismicity, and ocean-bottom microseism intervals.
- Add an LLM-as-judge fallback for subtle report-scoring failures.
