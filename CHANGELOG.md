# Changelog

All notable changes to **Repère** are recorded here. The format follows
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) and the
project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

Entries are written for downstream readers — researchers running the
benchmarks, contributors writing PRs, future Marine. The roadmap that
generated each release lives in [`ROADMAP.md`](ROADMAP.md); each item
there cross-references the version that delivered it.

## [Unreleased]

## [0.5.1] — 2026-09-22 — first PyPI release

### Added

- **Published to PyPI as [`repere`](https://pypi.org/project/repere/).**
  `pip install repere`. Uploaded by `.github/workflows/publish.yml` on a
  version tag through PyPI Trusted Publishing, so no API token exists
  anywhere; the job's OIDC token is exchanged for the upload credential. Four
  guards run before the publish job, because a PyPI version cannot be reused
  once uploaded: the tag must match `project.version`, `twine check` must pass
  on both artifacts, no `Requires-Dist` may carry a direct URL, and the wheel
  must load every suite's data files from a throwaway venv.
- **`[project]` metadata for the PyPI page.** `authors`, `keywords` (mirroring
  `CITATION.cff`), ten `classifiers`, and `[project.urls]` (Homepage,
  Repository, Documentation, Changelog, Issues). No
  `License :: OSI Approved :: MIT License` classifier: the license reaches
  PyPI as `License-Expression` under PEP 639, and setuptools>=77 errors out if
  a project declares both. No author email, since package metadata is
  published and scraped.

### Changed

- `description` is now "Cost-aware, rigor-preserving evaluation of scientific
  AI agents in the geosciences". It read "Cost-optimized multi-agent
  evaluation and routing prototype", which is the PyPI page's one-line summary
  and no longer described the project.

Why a new version rather than metadata on v0.5.0: that tag is public and the
sandbox image `ghcr.io/mdenolle/repere-sandbox:v0.5.0` is pinned to its
commit, so changing the metadata would have meant a distribution no git tag
reproduces. Nothing was ever uploaded to PyPI under 0.5.0, so 0.5.1 as the
first PyPI release leaves no visible gap.

## [0.5.0] — 2026-09-22 — the Repère rename

### Changed

- **Project renamed: FrugalMind → Repère.** Repère is French for a fixed
  survey benchmark marker — the shared reference every agent, regardless of
  size or cost, is measured against. Package and import paths changed from
  `frugalmind` / `frugalmind_suites` to `repere` / `repere_suites`
  (`src/frugalmind` → `src/repere`, `src/frugalmind_suites` →
  `src/repere_suites`); the `pyproject.toml` package name and the
  `frugalmind` CLI entry point renamed to `repere` (now `repere.cli:main`).
  The sandbox Docker image renamed from `ghcr.io/mdenolle/frugalmind-sandbox`
  to `ghcr.io/mdenolle/repere-sandbox`. Mechanical rename only — no
  behavioural change.

- **Environment variables renamed: `FM_*` → `REPERE_*`.** All 31 of them,
  same order and meaning: `REPERE_USE_DOCKER_SANDBOX`, `REPERE_SANDBOX_IMAGE`,
  `REPERE_OUT_DIR`, `REPERE_STALTA_GOLDEN_DIR`, `REPERE_STALTA_SPLIT`,
  `REPERE_EVAL_DATA_DIR`, `REPERE_RCA_PRIVATE_DIR` and the rest. **No
  back-compatibility shim**: the old names are read nowhere, and because every
  read site is an `os.environ.get(..., default)` an `FM_*` export left in a
  shell profile or a CI secret now falls through to the default silently
  instead of erroring. Re-export anything you had set. Historical entries
  below keep the `FM_*` spelling that shipped in 0.3.0 and 0.4.0.

- **Publishable on PyPI, which cost the `dvv` extra.** `pip install -e ".[dvv]"`
  is gone: it declared `codameter` as a direct git URL, and PyPI rejects
  direct-URL dependencies in uploaded metadata, extras included. The pin —
  still the immutable commit behind codameter v0.3.0, for the same reason as
  before — moved to `requirements-dvv.txt`, so the install is now
  `pip install -e . -r requirements-dvv.txt`. Updated in
  `.github/workflows/dvv-suite.yml`, `docs/dvv_suite_v0.md` and
  `docs/golden_data_provisioning.md`.
- **`[tool.setuptools.package-data]` now covers every suite.** It listed three
  patterns under `repere_suites.sta_lta` and nothing else, so a wheel built
  from this project shipped no `cases.yaml`, no RCA seeds, no schema, no
  pricing map and no corpora: it would import and then enumerate zero items in
  six of the seven suites. Only ever exercised through editable installs, where
  the source tree is on the path and the gap is invisible.
- **The sandbox image builds on every push to `main`.** The `on.push` paths
  filter also applied to tag pushes, and a release tag points at a version-bump
  commit that touches no Docker file, so the release image would never have
  been built. Filter kept on `pull_request`.

### Added

- **Repère-RCA design and skeleton.** `DESIGN.md` (taxonomy, tiers,
  architecture decision memo), `OPEN_QUESTIONS.md`, `docs/rca/` (inventory,
  authoring guide, ABC audit, prior-art notes, rubric stubs) and
  `src/repere_suites/rca/`: JSON-Schema golden-record contract with two
  shapes and an explicit verification tier, validator with rules R01 to R15,
  16 template seed records, frozen price map skeleton, cost layer with
  model-pin and price-verification flags, T2 checkers, T1 chronfix clock
  oracle, Inspect task and tier-dispatching scorer with a void taxonomy,
  runner with repeats and bootstrap CI (`rca.result.v0.1`), do-nothing and
  BM25-only baselines, pinned external-data fetch script, tests.
- `sandbox.run_snippet(..., input_files=...)` stages input files into the
  snippet's working directory (additive; default behaviour unchanged).
- `[rca]` optional extra (`jsonschema`, `numpy`).

Phase 3 work begins here. Candidate items: P3.1 submit STA/LTA as an
`inspect_evals` benchmark, P3.2 grow the truth set to 30–50 events,
P3.3 hidden test split, P3.4 skill-conditioned 3-axis leaderboard,
P3.5 per-suite `RUBRIC.md` scorer rationale.

## [0.4.0] — 2026-05-12 — Phase 2: AstaBench substrate alignment

> The framework now runs on the AstaBench / InspectAI substrate. Five
> Phase 2 items shipped: an InspectAI eval loop, a pinned Docker
> sandbox, a multi-step ReAct agent baseline, telemetry log records
> aligned with Inspect's `EvalSample` / `EvalOutput` schema, and a
> repository-specific Copilot review rubric. No breaking API changes
> for callers of the 0.3.x public surface — the `log_generation`
> alias is preserved and v1 telemetry logs read-compat.

### Added

- **JSONLTelemetry v2 schema** (P2.5). Field names now align with
  InspectAI's `EvalSample` / `EvalOutput` so FrugalMind logs map
  cleanly to Inspect's `.eval` shape. New `run_id` (UUID4) on every
  record; `task` / `task_args` / `solver` / `model` / `created` /
  `completed` on the run header; `id` / `epoch` / `output` per sample
  (renamed from `item_index` / `generation`). New `log_sample(...)`
  write method; `log_generation(...)` stays as an alias for back-compat.
  `read_jsonl(...)` gained a v1 → v2 normalisation shim
  (`normalise=False` returns raw on-disk records). Field-mapping table
  and versioning policy at [`docs/telemetry.md`](docs/telemetry.md).
  Test count: 230 → 242 (12 new telemetry tests).

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

- **Pinned Docker sandbox** (P2.2). New `docker/sandbox.Dockerfile`
  pins the execution environment for the STA/LTA suite scorers and the
  ReAct agent's `python_session` tool: `python:3.10-slim-bookworm` with
  `numpy==1.26.4`, `scipy==1.13.1`, `matplotlib==3.9.2`,
  `scikit-image==0.24.0`, `obspy==1.4.1`, `PyYAML==6.0.2`. Runs as
  non-root, ships with `tini` so host-side timeouts terminate the
  container cleanly, sets `MPLBACKEND=Agg`. `sandbox.py` learns an
  `FM_USE_DOCKER_SANDBOX=1` dispatch branch (image configurable via
  `FM_SANDBOX_IMAGE`, defaults to `ghcr.io/mdenolle/frugalmind-sandbox:latest`)
  that runs the snippet inside the container with `--network=none` and
  the host tmpdir mounted at `/work`. Default behaviour is unchanged —
  `FM_USE_DOCKER_SANDBOX` unset still runs the historical host-Python
  path. New `tests/test_docker_sandbox.py` (23 tests on dispatch / cmd
  construction / error paths, all pass without Docker installed) and
  `tests/test_sandbox_parity.py` (deterministic-snippet end-to-end
  parity test; docker leg skips when the daemon isn't reachable).
  `.github/workflows/sandbox-image.yml` builds on every PR touching
  the Dockerfile and pushes `latest` / `sha-…` / version tags to GHCR
  on main and on `v*` tag pushes, with buildx GHA cache.
  `.github/workflows/sandbox-parity.yml` runs the suite under both
  backends in CI on every relevant PR. Closes ROADMAP P2.2.

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

[Unreleased]: https://github.com/mdenolle/repere/compare/v0.5.1...HEAD
[0.5.1]: https://github.com/mdenolle/repere/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/mdenolle/repere/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/mdenolle/repere/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/mdenolle/repere/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/mdenolle/repere/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/mdenolle/repere/releases/tag/v0.1.0
