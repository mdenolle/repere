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

## Running local evals and viewing the dashboard

If you have an [Ollama](https://ollama.com) server running with at least
one model pulled (e.g. `ollama pull mistral`), you can populate the
leaderboard end-to-end from your own machine:

```bash
# 1. Verify the model is available.
curl -s http://localhost:11434/api/tags | python -m json.tool

# 2. Run the STA/LTA intent-extraction suite under two conditions
#    (generic vs skill-conditioned). Each writes one JSON result file
#    under results/.
pixi run -e full frugalmind run-ollama-intent \
    --model mistral:latest --condition generic
pixi run -e full frugalmind run-ollama-intent \
    --model mistral:latest --skill stalta-detection --skill-mode instructions

# 3. Optional baselines: a deterministic stub eval and the offline
#    skill-lift benchmark, also written to results/.
pixi run -e full frugalmind smoke-eval
pixi run -e full frugalmind run-skill-lift \
    --skill stalta-detection --output results/skill_lift_stalta.json

# 4. Aggregate every JSON file under results/ into the static dashboard
#    payload that the GitHub Pages app consumes.
pixi run -e full frugalmind export-leaderboard \
    --results-dir results --output site/data/leaderboard.json

# 5. Serve the dashboard locally and open it in a browser.
python -m http.server 8765 --directory site
# then visit http://localhost:8765/#leaderboard
```

Add more rows by pulling additional Ollama models (`ollama pull llama3.1:8b`,
`ollama pull qwen2.5:7b`) and repeating step 2 with `--model <id>`. Each
unique `(model, condition)` pair becomes its own row.

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

The STA/LTA suite uses two kinds of gold, and the leaderboard is a third
artifact derived from runs over those golds. All three are reproducible
from the scripts in [`scripts/`](scripts/), and each has a drift test that
fails when the artifact and its source diverge.

| Artifact | Where it lives | How to (re)build | Drift test |
|---|---|---|---|
| `(prompt, gold)` fixtures for intent / fetch_code / trigger_code / report | [`tests/fixtures/sta_lta.<suite>.json`](tests/fixtures/) | `python scripts/build_suite_fixtures.py` | [`tests/test_suite_fixtures.py`](tests/test_suite_fixtures.py) |
| Plot PNG goldens (public) | [`src/frugalmind_suites/sta_lta/data/golden/<id>.png`](src/frugalmind_suites/sta_lta/data/golden/) | `python scripts/build_plot_goldens.py` | [`tests/test_canonical_recipe.py`](tests/test_canonical_recipe.py) |
| Plot PNG goldens (private) | `$FM_STALTA_GOLDEN_DIR/<id>.png` (gitignored) | `python scripts/build_plot_goldens.py --private` | none — private; reviewed manually |
| Static leaderboard data | [`site/data/leaderboard.json`](site/data/leaderboard.json), [`site/data/skill_lift.json`](site/data/skill_lift.json) | `python scripts/build_site_data.py` | [`tests/test_site_data.py`](tests/test_site_data.py) |

### 1. Build the `(prompt, gold)` fixtures for the four parametric suites

Four of the five STA/LTA suites are parametric over `events.yaml` —
intent_extraction, fetch_code, trigger_code, and report all derive every
prompt and every gold answer at runtime from the same truth set. To get a
human-inspectable static view of what the benchmark asks each model:

```bash
python scripts/build_suite_fixtures.py
```

This writes one JSON file per suite under `tests/fixtures/`:

```text
tests/fixtures/
├── sta_lta.intent_extraction.json   # 6 items, JSON-shaped golds
├── sta_lta.fetch_code.json          # 6 items, code-execution scoring
├── sta_lta.trigger_code.json        # 6 items, code-execution scoring
└── sta_lta.report.json              # 6 items, lexical scoring
```

Each item looks like this (snippet from `sta_lta.intent_extraction.json`):

```json
{
  "item_index": 0,
  "prompt": "Extract a JSON object describing the FDSN waveform request for this analysis task:\n\nTask: M6.8 Nisqually deep intraslab earthquake\nOrigin time (UTC): 2001-02-28T18:54:32.8\nSuggested station: UW.LON..BHZ\nSuggested window: ±7.5 minutes around origin.\n\nReturn ONLY a JSON object with keys: network, station, location, channel, starttime, endtime. Use ISO-8601 timestamps.",
  "gold": {
    "network": "UW",
    "station": "LON",
    "location": "",
    "channel": "BHZ",
    "starttime": "2001-02-28T18:47:02.800000+00:00",
    "endtime": "2001-02-28T19:02:02.800000+00:00"
  }
}
```

The fixtures are not the gold; `events.yaml` is. The fixtures are a
**static rendering** of what the live suites currently emit, so reviewers
can read prompts and golds in a PR without running Python. If you change
`events.yaml` or a suite prompt template, regenerate the fixtures and
commit the diff in the same PR. `tests/test_suite_fixtures.py` will fail
until you do.

### 2. Build the plot PNG goldens

The fifth suite (plot) compares model output to a reference PNG via SSIM.
The generator is [`scripts/build_plot_goldens.py`](scripts/build_plot_goldens.py); it supports two
output modes (public vs private) and two data modes (real FDSN vs
deterministic synthetic):

```bash
# (A) Public goldens, real FDSN data — commits under data/golden/.
#     Use only for citable events that have been validated against a catalog.
python scripts/build_plot_goldens.py --only nisqually-2001 tohoku-2011-teleseism

# (B) Private goldens for VERIFY events still under validation.
#     Output dir is gitignored; FM_STALTA_GOLDEN_DIR points scorers at it.
FM_STALTA_GOLDEN_DIR=~/private/fm_goldens \
  python scripts/build_plot_goldens.py --private \
  --only pnsn-quiet-day-VERIFY mt-rainier-swarm-2024-VERIFY

# (C) Synthetic-data fallback for sandboxes / CI smoke. Deterministic.
#     Do NOT publish benchmark numbers against synthetic goldens.
python scripts/build_plot_goldens.py --synth --only nisqually-2001 tohoku-2011-teleseism
```

The recipe — preprocessing, STA/LTA, and the matplotlib layout — is pinned
in [`src/frugalmind_suites/sta_lta/recipe.py`](src/frugalmind_suites/sta_lta/recipe.py) and
shared by both data modes. The two-panel layout (waveform + STA/LTA, red
dashed vertical lines at trigger onsets, station/event title) matches what
the [`seismic-plotting`](.github/skills/seismic-plotting) skill instructs
models to produce.

> The two public goldens currently committed (`nisqually-2001.png`,
> `tohoku-2011-teleseism.png`) were generated in synthetic mode. Regenerate
> with mode (A) on a host with EarthScope/IRIS access before any
> leaderboard publication.

### 3. Build the static-site leaderboard data

After running real evals (or just the offline demo), refresh the JSON files
the GitHub-Pages site reads:

```bash
# Run the offline 3-small-models demo to produce results/demo_small_models.json:
python scripts/demo_small_models.py

# Or hit local Ollama instead:
python scripts/demo_small_models.py --live

# Then build the static-site data:
python scripts/build_site_data.py
```

This writes:

- `site/data/leaderboard.json` — main per-row leaderboard (rank, model,
  agent_condition, suite, score, cost, completed, efficiency).
- `site/data/skill_lift.json` — per-model lift table (`score_none`,
  `score_full`, `lift`, `cost_lift_pct`).

The HTML page at [`site/index.html`](site/index.html) renders both as two
separate tables. To preview locally:

```bash
cd site && python -m http.server 8123
# then open http://127.0.0.1:8123/
```

`tests/test_site_data.py` validates the schema of both JSON files and
checks that every `querySelector('#…')` in [`site/app.js`](site/app.js) has
a matching id in the HTML — a regression in either side of the contract
fails the test before it reaches Pages.

### Public-vs-private policy

- Commit small public fixtures, sample events, and PNG goldens for
  VERIFIED citable events (Nisqually 2001, Tōhoku 2011).
- Do not commit full private goldens, provider secrets, or paid-eval
  outputs.
- Point scorers at private STA/LTA goldens via `FM_STALTA_GOLDEN_DIR`; the
  generator's `--private` flag respects it.
- Store local eval outputs under `results/`, which is gitignored.
- Use GitHub Actions secrets for future private CI access.
- Promote generated artifacts to public goldens only after human review of
  the catalog match and the underlying waveform.

### Tests that protect each artifact

| Test file | What it checks |
|---|---|
| [`tests/test_suite_fixtures.py`](tests/test_suite_fixtures.py) | Each parametric suite's live items match the committed `(prompt, gold)` fixtures. Fails if `events.yaml` or a prompt template drifts. |
| [`tests/test_canonical_recipe.py`](tests/test_canonical_recipe.py) | The plot recipe is byte-deterministic (SSIM=1.0 self-match), positive synthetic events trigger, negative ones don't, both committed public PNGs exist. |
| [`tests/test_site_data.py`](tests/test_site_data.py) | `leaderboard.json` and `skill_lift.json` have the expected fields; `app.js` selectors all resolve in `index.html`. |
| [`tests/test_three_small_models.py`](tests/test_three_small_models.py) | The 3-small-models skill-lift demo runs end-to-end against the YAML registry and produces sane lift values. |

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

The current plan is in [`ROADMAP.md`](ROADMAP.md) — three phases of work
aligning FrugalMind with [AstaBench](https://allenai.org/asta/bench) and
[InspectAI](https://inspect.aisi.org.uk/) standards while keeping
FrugalMind's distinct identity (skills system, frugality-first framing,
parametric truth set, negative-case discipline). Each item is a candidate
GitHub issue under the `astabench-alignment` label; bootstrap them with:

```bash
bash scripts/create_roadmap_issues.sh           # all items
bash scripts/create_roadmap_issues.sh --dry-run # preview only
bash scripts/create_roadmap_issues.sh --only P1.1 P1.3
```

The script is idempotent: re-running it updates existing issues by `[Px.y]`
title prefix rather than creating duplicates. New issues should follow the
roadmap-item template at
[`.github/ISSUE_TEMPLATE/roadmap_item.yml`](.github/ISSUE_TEMPLATE/roadmap_item.yml).
