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
│   └── frugalmind_suites/
│       └── sta_lta/                 # First scientific benchmark suite
├── tests/                           # Deterministic smoke tests
├── docs/                            # Archived suite docs and design notes
├── site/                            # GitHub Pages leaderboard
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
pixi run test
pixi run smoke-eval
pixi run export-leaderboard
```

`pixi run test` runs only deterministic tests. It does not need ObsPy, network access, model-provider credentials, or private goldens.

`pixi run smoke-eval` runs a local stub evaluation and writes an ignored JSON result under `results/`.

`pixi run export-leaderboard` converts local JSON results into `site/data/leaderboard.json` for the static leaderboard.

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

## Current benchmark suite

The STA/LTA suite tests a seismic analysis pipeline:

1. Intent extraction from natural language to FDSN query JSON.
2. ObsPy waveform-fetch code generation.
3. STA/LTA trigger code generation.
4. Plot generation and comparison to approved goldens.
5. One-paragraph technical reporting.

The public sample truth set currently has six events across regional earthquakes, teleseisms, noise days, and quarry blasts. Several entries are marked `VERIFY`; do not publish benchmark numbers until those catalog entries are validated.

## Private golden datasets

FrugalMind should use public sample data for development and private/full golden datasets for serious model comparison.

Policy:

- Commit small public fixtures and sample events.
- Do not commit full private goldens, provider secrets, or paid-eval outputs.
- Point local runs to private STA/LTA goldens with `FM_STALTA_GOLDEN_DIR`.
- Store local eval outputs under `results/`, which is ignored by git.
- Use GitHub Actions secrets for future private CI access.
- Promote generated artifacts to goldens only after human review.

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

## Roadmap

- Expand the core framework with real provider adapters.
- Add cost-aware routing and subagent rigor policies.
- Validate all public sample events against source catalogs.
- Add private full-suite golden datasets.
- Add additional scientific and engineering benchmark suites.
- Add model registry and budget configuration files.
- Enable weekly evals once the manual workflow is stable.
