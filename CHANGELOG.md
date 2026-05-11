# Changelog

All notable changes to **FrugalMind** are recorded here. The format follows
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) and the
project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

Entries are written for downstream readers — researchers running the
benchmarks, contributors writing PRs, future Marine. The roadmap that
generated each release lives in [`ROADMAP.md`](ROADMAP.md); each item
there cross-references the version that delivered it.

## [Unreleased]

Phase 2 work begins here. Candidate items: P2.1 InspectAI substrate
(shipped, in review), P2.2 pinned sandbox Dockerfile, P2.4 multi-step
ReAct agent baseline (shipped on `p2-4-react-baseline`, stacked on P2.1).

### Added

- **ReAct multi-step agent baseline** (P2.4). New `frugalmind.agents`
  subpackage with three Inspect tools (`fdsn_get_waveforms`,
  `python_session`, `record_submit`) and a `stalta_react` solver wrapping
  Inspect's `basic_agent`. Addressable as
  `inspect eval src/frugalmind_suites/sta_lta/inspect_tasks.py@<task> \
   --solver src/frugalmind/agents/react.py@stalta_react`. The package
  re-exports a static `stalta_tools_dict()` descriptor that is importable
  without `inspect_ai`. New notebook
  `notebooks/03_react_baseline.ipynb` walks through the tools, solver,
  and a free `mockllm/model` dry-run before the live-provider swap.
  Builder script `notebooks/_build_react_baseline.py` is the source of
  truth.

## [0.3.0] — Phase 1: AstaBench-alignment quick wins

> **Pending tag** — to be cut once P1.3, P1.4, and P1.5 merge to main.

### Added

- **Split + visibility on `events.yaml`** (P1.1). Every event now carries
  `split: validation | test` and `visibility: public | private`. Suites
  filter by both via `STALTAIntentExtractionSuite(split="validation")` or
  the `FM_STALTA_SPLIT` environment variable. Fixtures dumped per-(suite,
  split) under `tests/fixtures/sta_lta.<suite>.<split>.json`.
- **Cutoff-date metadata** (P1.2). New `cutoff_date: YYYY-MM-DD` field on
  every event. Loader fills missing values with `origin_time + 7d` for
  positive cases and `origin_time - 1d` for negatives. Public helper:
  `frugalmind_suites.sta_lta.items.default_cutoff_date(event)`. Disclosure
  added to all five suite prompts.
- **AstaBench-style row metadata** (P1.3). `openness` and `toolset`
  columns on `LeaderboardRow` and `SkillLiftRow`, on `site/data/*.json`,
  and as pill-rendered columns in both site tables. Vocabulary follows
  AstaBench: `open-source-open-weight`, `open-source-closed-weight`,
  `closed-source-api`, `closed-source-ui`, `unknown` for openness;
  `standard`, `custom-interface`, `custom`, `unknown` for toolset. All 13
  cards in `config/models.yaml` declare `metadata.openness`.
- **Cost-vs-quality Pareto chart** (P1.4). New panel on the static site
  with a Chart.js scatter plot; non-dominated rows highlighted in green,
  dominated rows faded gray. `app.js` exposes `computeParetoFront(rows)`
  for reuse. Loaded from cdnjs (`Chart.js@4.4.4`).
- **Optional LLM-judge fallback for the report scorer** (P1.5).
  `make_report_scorer(judge_adapter=…, judge_threshold=0.5)` calls the
  judge only when the lexical score falls below the threshold; final
  score is `max(lexical, judge)` so a model whose lexical was already OK
  is never demoted. Judge prompt pinned at
  `src/frugalmind_suites/sta_lta/judge_prompts/report_scorer.md`.
  Default behaviour (no adapter) is byte-identical to 0.2.0.
- **Drift tests** for the new artifacts: `tests/test_judge_fallback.py`
  (22 cases), Pareto-chart pinning in `tests/test_site_data.py` (3
  cases), pill / column / CSS-variable contracts (3 cases), event-shape
  hardening in `tests/test_event_validation.py` (29 cases), cutoff-date
  rule check in `tests/test_cutoff_date.py` (10 cases).
- **Test count: 149 → 171** across all of Phase 1.

### Changed

- `_load_events` validates the full top-level required-key list plus
  nested `stalta_params` (sta/lta/on_thresh/off_thresh) and each
  `recommended_stations` entry (network/station/location/channel). Errors
  always include the offending event id and list index. Non-mapping
  entries are caught with an `isinstance(ev, dict)` guard before any
  `ev.get()` call.
- `scripts/create_roadmap_issues.sh` declares its `jq` and `python3`
  dependencies and checks for them at runtime; replaces the old `tr`-based
  anchor slug with a Python regex that mirrors GitHub's actual heading-id
  rule (drops `.`, backticks, `·`; collapses runs).

### Fixed

- mt-rainier-swarm-2026, pnsn-quiet-day, cascade-quarry-blast, and
  low-lf-volcano-snr cutoff_dates now match the default rule (hotfix
  after the JSONL exporter merge updated origin times without recomputing
  cutoffs).
- `scripts/build_suite_fixtures.py` regenerates 8 fixture JSONs (4 suites
  × 2 splits) and the drift test catches subsequent staleness loudly.
- Pareto chart inherits site CSS variables (`--text`, `--muted`,
  `--line`) instead of the Anthropic-design-system names that didn't
  exist in `styles.css`; fallback colors updated to dark-theme-readable
  values. Pareto panel metadata spans now also clear in the leaderboard
  load-failure path.
- `LeaderboardRunner.run` tags `SkillLiftRow.toolset` as
  `"custom-interface"` (the runner always exercises a skill); was
  `"standard"`, which misled AstaBench-style comparisons.
- `_call_judge` wraps `template.format(...)` inside its `try/except` so a
  malformed template returns `0.0` instead of raising. `make_report_scorer`
  wraps eager template loading similarly so a missing prompt file silently
  disables the judge path rather than aborting eval.

## [0.2.0] — Phase 0: framework rebuild

### Added

- **Framework primitives.** `BudgetGuard`, `JSONLTelemetry`,
  `AnthropicAdapter`, `OpenAICompatAdapter`, `EchoAdapter`,
  `adapter_from_env`. All exposed via `frugalmind.*` lazy re-exports.
- **`FrugalRouter`** picks the cheapest model meeting a per-task quality
  floor; EMA-based score updates; configurable fallback policy; integrates
  with `BudgetGuard`.
- **`LeaderboardRunner`** runs a suite under skill modes `none` and `full`
  and emits a `SkillLiftRow` per model carrying both quality scores and
  cost.
- **13-model registry** at `config/models.yaml` across nano / small /
  medium / big / cloud tiers (qwen, mistral, llama, gemma, claude, gpt).
  Loader: `frugalmind.registry.load_registry_yaml`.
- **Skill system.** `SkillLoader` with three injection modes (`none`,
  `instructions`, `full`), `SkillManifest` binding skills to suite IDs,
  four full skills under `.github/skills/`: `stalta-detection`,
  `obspy-fdsn-fetch`, `seismic-plotting`, `seismic-report`. All follow the
  Anthropic Agent Skills format with frontmatter, references, examples,
  validators.
- **Canonical plot recipe** at `src/frugalmind_suites/sta_lta/recipe.py`
  pinning the STA/LTA plot layout used by the plot-suite SSIM scorer.
  Two public PNG goldens (Nisqually 2001, Tōhoku 2011) plus two private
  goldens.
- **Static GitHub Pages site** under `site/` with leaderboard + skill-lift
  tables, JSON data files at `site/data/`, and `scripts/build_site_data.py`
  to refresh from `results/`.
- **JSONL exporter** for benchmark artifacts (`src/frugalmind/export.py`)
  producing per-suite JSONL plus a manifest with SHA-256 hashes.
- **Notebooks** `01_skill_lift_quickstart.ipynb` (offline 3-small-model
  demo) and `02_stalta_golden_explorer.ipynb` (interactive FDSN
  golden-dataset builder).
- **Tests, scripts, CI scaffold.** `scripts/build_plot_goldens.py`,
  `scripts/build_suite_fixtures.py`, `scripts/demo_small_models.py`,
  `scripts/create_roadmap_issues.sh`, `.github/ISSUE_TEMPLATE/`,
  `ROADMAP.md`, `notebooks/README.md`. ~145 deterministic tests.

### Changed

- Suite ID standardised to `sta_lta.intent_extraction` everywhere
  (`leaderboard.DEFAULT_SUITE`, `cli.py`, fixtures).
- `pyproject.toml` bumped to 0.2.0; added MIT license; ruff lint config
  selecting E, F, I, B, UP rule sets.

### Fixed

- STA/LTA datetime parser tolerates 1-9 fractional digits in
  `origin_time` so events with values like `2001-02-28T18:54:32.8` load
  on Python 3.10 (was rejected pre-3.11).
- `src/frugalmind.egg-info/` and `.DS_Store` removed from version
  control; `.gitignore` already covered both.

## [0.1.0] — Initial scaffold

### Added

- Original repo structure with `src/frugalmind/` core primitives:
  `TaskKind`, `DenolleGroupSuite`, `ModelCard`, `ModelRegistry`,
  `EvalRunner`, `Generation`, `Adapter` (Protocol), `EvalResult`.
- STA/LTA benchmark suite with five task kinds (intent extraction,
  fetch code, trigger code, plot, report) parametric over `events.yaml`.
- Six sample events in `events.yaml` (Nisqually 2001, Tōhoku 2011, plus
  four `VERIFY` placeholders).
- Subprocess sandbox for code-execution scoring (`sandbox.py`,
  `extract_code`, `run_snippet`).
- Initial `seismo-data-agent/SKILL.md` (later superseded by the four
  skills in 0.2.0).
- Pixi + conda dev environments, manual `pages.yml` and `evals.yml`
  workflows, README sketch.

[Unreleased]: https://github.com/mdenolle/frugalmind/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/mdenolle/frugalmind/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/mdenolle/frugalmind/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/mdenolle/frugalmind/releases/tag/v0.1.0
