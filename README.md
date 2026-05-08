# FrugalMind

FrugalMind is a prototype for a cost-optimized multi-agent evaluation and routing system. The goal is to preserve scientific rigor while spending the least possible model budget by routing work to the cheapest agent that can meet a task-specific quality floor.

The current repository contains:

- A minimal core evaluation framework in `src/frugalmind`.
- The first benchmark suite, STA/LTA seismic detection, in `src/frugalmind_suites/sta_lta`.
- Public sample fixtures for local development.
- A private-golden-data policy for hidden evaluation sets.
- A static leaderboard app in `site/` for GitHub Pages.
- Manual CI scaffolding for smoke tests and future scheduled evals.

## Why this exists

Multi-agent systems often use expensive frontier models for every step, even when a smaller model is good enough for extraction, plotting, code generation, or reporting. FrugalMind aims to learn and enforce task-specific quality floors from hidden/private golden datasets, then route subagent work by cost subject to rigor constraints.

Initial focus:

1. Define reproducible benchmark suites with deterministic scorers where possible.
2. Maintain public sample fixtures for development.
3. Keep full golden datasets private to reduce overfitting.
4. Run evals on demand first.
5. Promote to scheduled weekly GitHub Actions evals when provider credentials, budgets, and private data access are ready.

## Repository layout

```text
frugalmind/
├── src/
│   ├── frugalmind/                  # Core eval primitives and CLI
│   │   ├── adapters.py              # AnthropicAdapter, OpenAICompatAdapter, EchoAdapter
│   │   ├── budget.py                # BudgetGuard
│   │   ├── leaderboard.py           # LeaderboardRunner + skill-lift export
│   │   ├── registry.py              # YAML model-registry loader
│   │   ├── router.py                # FrugalRouter
│   │   ├── skills.py                # SkillLoader, SkillManifest, render modes
│   │   └── telemetry.py             # JSONLTelemetry
│   └── frugalmind_suites/
│       └── sta_lta/                 # First scientific benchmark suite
├── config/
│   └── models.yaml                  # 13-model registry (nano/small/medium/big/cloud)
├── notebooks/                       # Interactive walkthroughs (quickstart, etc.)
├── scripts/                         # Small standalone runners
├── tests/                           # Deterministic test suite (~80 tests)
├── docs/                            # Archived suite docs and design notes
├── site/                            # GitHub Pages leaderboard
├── .github/skills/                  # Domain-agent skills + manifest.yaml
├── .github/workflows/               # Manual CI scaffold
├── pyproject.toml                   # Python package metadata
├── pixi.toml                        # Primary development environment
└── environment.yml                  # Conda fallback
```

The original STA/LTA suite README has been preserved in `docs/sta_lta_suite_v0.md`.

## Quickstart with Pixi

Install Pixi, then run:

```bash
pixi install
pixi run test                # deterministic test suite (~80 tests, no providers)
pixi run smoke-eval          # stub eval; writes results/stub_eval.json
pixi run export-leaderboard  # builds site/data/leaderboard.json
```

`pixi run test` does not need ObsPy, network access, model-provider
credentials, or private goldens.

The CLI also exposes:

```bash
pixi run frugalmind list-models             # print the loaded model registry
pixi run frugalmind list-skills             # print skills + their suite bindings
pixi run frugalmind run-skill-lift          # offline skill-lift demo
pixi run frugalmind run-ollama-intent --model mistral:7b --skill stalta-detection
```

## Conda fallback

If Pixi is unavailable:

```bash
conda env create -f environment.yml
conda activate frugalmind
python -m pip install -e .
python -m pytest
python -m frugalmind.cli smoke-eval
python -m frugalmind.cli export-leaderboard
```

## Notebooks

The fastest way to see the framework in action is the quickstart notebook:

```bash
pip install -e ".[dev]" jupyter
jupyter lab notebooks/
```

Then open [`notebooks/01_skill_lift_quickstart.ipynb`](notebooks/01_skill_lift_quickstart.ipynb).
It walks through three small-tier models (`mistral:7b`, `llama3.1:8b`,
`qwen2.5:7b`) running the public STA/LTA intent-extraction suite under
`none` vs `full` skill conditions and produces a leaderboard JSON. The
default path uses an `EchoAdapter` so it runs offline; the last section
shows how to swap to a live Ollama server with a one-line factory change.

To run the same demo from the command line without the notebook:

```bash
python scripts/demo_small_models.py            # offline stub demo
python scripts/demo_small_models.py --live     # uses local Ollama
```

See [`notebooks/README.md`](notebooks/README.md) for more.

## Current benchmark suite

The STA/LTA suite tests a seismic analysis pipeline:

1. Intent extraction from natural language to FDSN query JSON.
2. ObsPy waveform-fetch code generation.
3. STA/LTA trigger code generation.
4. Plot generation and comparison to approved goldens.
5. One-paragraph technical reporting.

The public sample truth set currently has six events across regional earthquakes, teleseisms, noise days, and quarry blasts. Several entries are marked `VERIFY`; do not publish benchmark numbers until those catalog entries are validated.

The rationale for starting with STA/LTA is documented in `docs/stalta_benchmark_rationale.md`. In short, this is the smallest complete earthquake-seismology coding pipeline: fetch waveform data, detect a possible event, plot the result, and explain whether the source is plausibly local/regional, teleseismic, anthropogenic, or noise.

A draft seismology domain skill is available at `.github/skills/seismo-data-agent/SKILL.md`. Runs that use it should be labeled separately from raw coding-agent runs, for example with `agent_condition = "SeismoDataAgent+skill-v0.1-draft"`. Leaderboard condition metadata are described in `docs/leaderboard_conditions.md`.

## Golden datasets

The STA/LTA suite has two kinds of gold:

1. **Parametric gold** (intent, fetch_code, trigger_code, report). Each suite
   derives `(prompt, gold)` directly from `events.yaml`. Adding an event to
   `events.yaml` produces 5 graded items automatically. Static dumps of
   every `(prompt, gold)` pair live under [`tests/fixtures/`](tests/fixtures/) so reviewers can
   inspect what the benchmark actually asks for, and a drift test
   ([`tests/test_suite_fixtures.py`](tests/test_suite_fixtures.py)) fails when the live items diverge from the dump.

2. **Plot gold** (the plot suite only). The gold is a PNG produced by the
   canonical recipe in [`src/frugalmind_suites/sta_lta/recipe.py`](src/frugalmind_suites/sta_lta/recipe.py). SSIM scoring
   compares model output to that PNG with a 0.85 threshold.

### Building plot goldens

The generator is [`scripts/build_plot_goldens.py`](scripts/build_plot_goldens.py). It supports two output
modes (public vs private) and two data modes (real FDSN vs deterministic
synthetic):

```bash
# Public goldens, real FDSN data (committed under data/golden/)
python scripts/build_plot_goldens.py --only nisqually-2001 tohoku-2011-teleseism

# Private goldens for VERIFY events still being validated (gitignored output dir)
FM_STALTA_GOLDEN_DIR=~/private/fm_goldens \
  python scripts/build_plot_goldens.py --private \
  --only pnsn-quiet-day-VERIFY mt-rainier-swarm-2024-VERIFY

# Sandbox / CI smoke (no network, deterministic synthetic data)
python scripts/build_plot_goldens.py --synth --only nisqually-2001 tohoku-2011-teleseism
```

Synthetic mode produces structurally correct placeholder PNGs (right
panels, correct title format, working triggers) so the suite has *something*
to compare against during local development. **Never publish benchmark
numbers against synthetic goldens** — regenerate from real FDSN data on a
host with network access first.

The two committed public goldens (`nisqually-2001.png`, `tohoku-2011-teleseism.png`)
in this repo were generated in synthetic mode for the initial commit; they
must be regenerated from real FDSN before any leaderboard publication.

### Regenerating the parametric fixtures

If you change `events.yaml` or any of the suite prompt templates, regenerate
the static fixtures:

```bash
python scripts/build_suite_fixtures.py
```

Then review the diff under `tests/fixtures/` and commit it as part of the
same PR. The drift test will keep failing until you do.

### Public-vs-private policy

- Commit small public fixtures, sample events, and goldens for VERIFIED
  citable events (e.g. Nisqually 2001, Tōhoku 2011).
- Do not commit full private goldens, provider secrets, or paid-eval
  outputs.
- Point local runs to private STA/LTA goldens with `FM_STALTA_GOLDEN_DIR`;
  the generator's `--private` flag respects this.
- Store local eval outputs under `results/`, which is gitignored.
- Use GitHub Actions secrets for future private CI access.
- Promote generated artifacts to public goldens only after human review of
  the catalog match and the underlying waveform.

## Manual evals now, weekly later

The initial workflow is manual by design. The GitHub Actions scaffold supports `workflow_dispatch` and runs smoke tests by default. A weekly schedule is included as a commented scaffold for later activation once costs, secrets, and private data access are configured.

## Live leaderboard

The static leaderboard lives in `site/` and is deployed by `.github/workflows/pages.yml` using GitHub Pages. On each push to `main`, the workflow runs tests, generates a public smoke leaderboard, and deploys the static site artifact.

To update the leaderboard locally:

```bash
pixi run smoke-eval
pixi run export-leaderboard
```

For GitHub, set Pages to deploy from GitHub Actions if it is not already enabled in repository settings. Private golden-set results should only be exported into the public site after human approval.

Leaderboard rows include an `agent_condition` field so a raw `generic-coding-agent` run is not mixed with a `SeismoDataAgent+skill-v0.1-draft` run. Skill-assisted runs may also include `skill_name` and `skill_version`.

## Roadmap

Done:

- Provider adapters for Anthropic Messages API and OpenAI-compatible chat completions.
- `FrugalRouter` with per-task quality floors, EMA score updates, and budget integration.
- `BudgetGuard` and `JSONLTelemetry` modules.
- 13-model registry (`config/models.yaml`) with cost metadata across nano/small/medium/big/cloud tiers.
- Skill system: `SkillLoader` with `none`/`instructions`/`full` modes, `manifest.yaml` binding skills to suites, four full skills (`stalta-detection`, `obspy-fdsn-fetch`, `seismic-plotting`, `seismic-report`).
- `LeaderboardRunner` that computes per-model **skill lift** between baseline and skill-loaded conditions.

Next:

- Validate all public sample events against source catalogs (lift the four `VERIFY` placeholders).
- Add private full-suite golden datasets.
- Add additional scientific and engineering benchmark suites beyond STA/LTA.
- Hook the `FrugalRouter` into a real benchmark loop (currently independent of `EvalRunner`).
- Promote the legacy `seismo-data-agent` rows in the leaderboard to `stalta-detection` once verified.
- Enable weekly evals once the manual workflow is stable.
