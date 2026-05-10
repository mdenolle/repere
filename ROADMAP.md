# FrugalMind roadmap

This document is the canonical plan for FrugalMind. Each item below corresponds
one-to-one with a GitHub issue under the `astabench-alignment` label; the issue
links back to the section here. The roadmap is the **planning view**; the
issues are the **execution view**.

## Goal

Bring FrugalMind's eval framework into alignment with the standards established
by [AstaBench](https://allenai.org/asta/bench) and [InspectAI](https://inspect.aisi.org.uk/),
without giving up the three things that make FrugalMind distinct:

- a **frugality-first** framing (skill-lift, cost-Pareto, BudgetGuard);
- a **parametric truth set** (`events.yaml` → 5 derived suites);
- **negative-case discipline** (no-event windows are first-class items).

Anything that conflicts with those three is a deal-breaker. Everything else is
on the table.

## Phases

- **Phase 1 — Quick wins.** No architectural risk. Adds AstaBench-style
  metadata, splits, and Pareto framing to the existing framework. ~1 week
  total if done sequentially.
- **Phase 2 — Medium changes.** Substrate-level: adopt InspectAI as the eval
  loop, ship a pinned sandbox, version the data, build a real multi-step
  agent baseline. ~3–4 weeks.
- **Phase 3 — Larger pivots.** Submit STA/LTA as an `inspect_evals`
  benchmark, scale the truth set to ~50 events, hide the test split,
  reframe the leaderboard around skill-lift. ~6–8 weeks.

## Tracking conventions

- **Milestones**: `Phase 1 — Quick wins`, `Phase 2 — Medium`, `Phase 3 — Pivots`.
- **Labels**: `astabench-alignment`, plus one `area:…` label and one `effort:S|M|L` label.
- **Project board**: simple Kanban (Backlog / Up next / In progress / Done) filtered to `astabench-alignment`.
- **Issue template**: [`.github/ISSUE_TEMPLATE/roadmap_item.yml`](.github/ISSUE_TEMPLATE/roadmap_item.yml).
- **Bootstrap**: `bash scripts/create_roadmap_issues.sh` creates labels, milestones, and all issues at once (requires `gh` CLI authenticated).

Each item below uses the structure:

> **Goal** · one-liner.
> **Why** · short paragraph linking to the AstaBench standard it tracks.
> **Deliverables** · the files/tests/code that prove it's done.
> **Acceptance** · observable criteria (test names, leaderboard fields, etc.).
> **Effort** · S (≤1 day), M (2–5 days), L (≥1 week).
> **Depends on** · earlier roadmap items, if any.
> **Tracking** · GitHub issue ref (filled in once the bootstrap script has run).

## Phase 0 — Current state (delivered, for reference)

These shipped during the bring-up sessions and are the baseline this roadmap
builds on:

- Framework primitives: `BudgetGuard`, `JSONLTelemetry`, `AnthropicAdapter`,
  `OpenAICompatAdapter`, `EchoAdapter`, `FrugalRouter`, `LeaderboardRunner`.
- 13-model registry at `config/models.yaml` (nano/small/medium/big/cloud).
- 4 skills with full Anthropic Agent Skill frontmatter + manifest binding
  skills to suites.
- Parametric `(prompt, gold)` fixtures for 4 suites under `tests/fixtures/`,
  protected by drift tests.
- Canonical plot recipe + 2 public + 2 private synthetic plot goldens.
- Static GitHub Pages site with main leaderboard + skill-lift table.
- 97 deterministic tests; offline notebook; offline `scripts/demo_small_models.py`.

---

# Phase 1 — Quick wins

## P1.1 · Add `split` and `visibility` to `events.yaml`

> **Goal** Tag every event as `split: validation | test` and
> `visibility: public | private`. Suites emit only the requested subset.
>
> **Why** AstaBench ships every benchmark with `validation` and `test` splits
> (e.g. `astabench/discoverybench_validation`). FrugalMind currently has one
> bucket, so any model that overfits to `nisqually-2001` looks great forever.
>
> **Deliverables**
> - New required fields on every event in `events.yaml`.
> - `_load_events(split=…)` in `items.py`; `EVENTS_PATH` honours
>   `FM_STALTA_SPLIT` env var.
> - Fixture dumper writes `tests/fixtures/sta_lta.<suite>.<split>.json`.
> - Suite tests parameterised on split.
>
> **Acceptance**
> - `STALTAIntentExtractionSuite(split="validation").items()` returns 2
>   events; `split="test"` returns 4.
> - Drift test passes for both splits.
> - `events.yaml` schema doc updated.
>
> **Effort** S
> **Depends on** none
> **Tracking** branch `p1-1-events-yaml-split` · issue _(file with `bash scripts/create_roadmap_issues.sh --only P1.1` and link here)_ · status: implementation complete on branch, awaiting issue file + PR

## P1.2 · Add `cutoff_date` per event

> **Goal** Record the date past which a retrieval-augmented agent must not
> query (catalogs, papers, network status pages).
>
> **Why** AstaBench enforces date cutoffs on its literature-search tools so
> tasks remain valid as new content appears. We don't have RAG agents yet,
> but recording the field now means we don't have to retrofit later.
>
> **Deliverables**
> - `cutoff_date: YYYY-MM-DD` field on every event.
> - Default in YAML loader: `origin_time + 7d` for positive cases,
>   `origin_time - 1d` for negative cases.
> - Pass-through field in fixtures and skill prompts.
>
> **Acceptance**
> - Every event has `cutoff_date`.
> - A new test verifies the default rule for a synthetic event.
>
> **Effort** S
> **Depends on** P1.1 (so we don't churn the YAML twice)
> **Tracking** branch `p1-2-cutoff-date` (stacked on `p1-1-events-yaml-split`) · issue _(file with `bash scripts/create_roadmap_issues.sh --only P1.2`)_ · status: implementation complete on branch, awaiting issue file + PR

## P1.3 · Add `openness` and `toolset` metadata to leaderboard rows

> **Goal** Every row on the static leaderboard declares which AstaBench
> openness and toolset category it falls into so two rows aren't compared
> apples-to-oranges.
>
> **Why** AstaBench requires both at submission time and shows them on the
> leaderboard. Without them, a "raw GPT-4o" row and a "ReAct + custom
> sandbox" row look equivalent and aren't.
>
> **Deliverables**
> - New columns in `LeaderboardRow`: `openness`, `toolset`.
> - `models.yaml` cards gain a `metadata.openness` (open-weight / open-source / closed-api / closed-ui).
> - `build_site_data.py` emits both fields; defaults `toolset: standard`.
> - HTML adds two columns; CSS for category pills.
> - `tests/test_site_data.py` asserts every row has both.
>
> **Acceptance** Leaderboard JSON, leaderboard HTML, and skill-lift JSON
> all carry the two fields.
>
> **Effort** S
> **Depends on** none
> **Tracking** branch `p1-3-leaderboard-metadata` · status: implementation complete on branch, awaiting issue file + PR

## P1.4 · Cost-vs-quality Pareto chart on the leaderboard

> **Goal** Add a scatter chart to the static site that puts cost on one axis,
> quality on the other, and draws the Pareto front.
>
> **Why** This is FrugalMind's whole thesis, but the current leaderboard
> ranks primarily by score. A Pareto plot shows budget-conscious choices at
> a glance and matches AstaBench's framing of cost as a first-class axis.
>
> **Deliverables**
> - Chart.js inline (the only allowed external CDN per the artifact rules
>   we set in earlier sessions).
> - New `<canvas>` panel in `index.html`.
> - `app.js` computes the front client-side from `leaderboard.json`.
>
> **Acceptance**
> - Chart renders for every leaderboard row.
> - Pareto front is highlighted; non-Pareto rows are faded.
> - `tests/test_site_data.py` adds a smoke test that the chart panel is
>   present in the HTML.
>
> **Effort** M
> **Depends on** P1.3 (cost units are now standardised across rows)
> **Tracking** _(issue not yet filed)_

## P1.5 · LLM-judge fallback for the report scorer

> **Tracking** branch `p1-5-judge-fallback` (off main) · status: implementation complete on branch, 20 new tests, 169 total passing
>
> **Goal** When the lexical report scorer returns < 0.5, optionally route to
> an LLM judge with a tight rubric.
>
> **Why** AstaBench's scorers escalate from deterministic to LLM-judge for
> open-ended outputs. Our report scorer is purely lexical and misses
> well-written but novel phrasings. Keep the lexical scorer authoritative
> by default; the judge is an opt-in.
>
> **Deliverables**
> - `make_report_scorer(judge_adapter=None, judge_threshold=0.5)`.
> - Judge prompt under `src/frugalmind_suites/sta_lta/judge_prompts/`,
>   pinned and tested for shape (not output).
> - Off by default; CI never calls the judge.
>
> **Acceptance**
> - When `judge_adapter` is supplied and lexical < 0.5, the scorer calls it.
> - When omitted, behaviour is byte-identical to today.
> - New unit test mocks the judge and asserts the threshold logic.
>
> **Effort** M
> **Depends on** none
> **Tracking** _(issue not yet filed)_

---

# Phase 2 — Medium changes

## P2.1 · Adopt InspectAI as the substrate

> **Tracking** branch `p2-1-inspect-substrate` (off main) · status: implementation complete on branch, 14 new tests, 189 total passing. `python -m inspect_ai list tasks src/frugalmind_suites/sta_lta/inspect_tasks.py` discovers all 5 tasks.


> **Goal** Convert each STA/LTA suite to an `inspect_ai.task.Task` with
> `Sample(input=prompt, target=gold, metadata=…)` records and an
> `@scorer`-decorated wrapper around our existing scorers.
>
> **Why** Adopting InspectAI gets us:
> - free `inspect view` log inspection;
> - a real `TaskState` so we can support multi-step agents that call tools;
> - compatibility with AstaBench's submission tooling and any future
>   `inspect_evals` listing.
>
> The cost is reorganising the suite layer; scorers, sandbox, and skills
> all carry over unchanged.
>
> **Deliverables**
> - `src/frugalmind_suites/sta_lta/inspect_tasks.py` exposing five `@task`
>   functions.
> - Scorer wrappers that call our existing `make_*` scorers.
> - `EvalRunner`, `LeaderboardRunner`, and `BudgetGuard` adapted to use
>   Inspect's run loop, or wrapped to coexist.
> - Optional `inspect_ai` dep behind an `eval` extra in `pyproject.toml`.
>
> **Acceptance**
> - `inspect eval frugalmind/sta_lta_intent_extraction --solver generate
>   --model openai/gpt-4o-mini --limit 1` runs end-to-end.
> - `inspect view logs/*.eval` opens a usable log.
> - Existing 97 tests still pass.
>
> **Effort** L
> **Depends on** P1.1, P1.2, P1.3
> **Tracking** _(issue not yet filed)_

## P2.2 · Pinned sandbox Dockerfile

> **Goal** A single image used by every code/plot/trigger task with
> `obspy`, `matplotlib`, `numpy`, `scikit-image`, `pyyaml` pinned to known
> versions.
>
> **Why** Today the sandbox is `subprocess.run(sys.executable, …)` against
> whatever the host has. AstaBench publishes a Dockerfile and runs every
> task inside it, which kills the entire "works on my machine" failure
> mode and makes scoring reproducible.
>
> **Deliverables**
> - `docker/sandbox.Dockerfile` with pinned deps.
> - `src/frugalmind_suites/sta_lta/sandbox.py` learns to dispatch to the
>   image when `FM_USE_DOCKER_SANDBOX=1`.
> - CI builds and caches the image.
>
> **Acceptance**
> - Plot and code suites pass identically with and without
>   `FM_USE_DOCKER_SANDBOX`.
> - The image is published as a GHCR artifact on tag.
>
> **Effort** M
> **Depends on** P2.1 (so the Inspect runner is the integration point)
> **Tracking** _(issue not yet filed)_

## P2.3 · Move large goldens to DVC or HuggingFace

> **Goal** Public PNG goldens are tracked outside git once the truth set
> exceeds ~25 events.
>
> **Why** AstaBench uses DVC + a gated HuggingFace dataset. With 50+ events
> and SSIM-checked PNG goldens at ~100 KB each, git history bloats fast.
>
> **Deliverables**
> - DVC config tracking `data/golden/` and the private equivalent.
> - Public goldens published as a HuggingFace dataset
>   `your-org/frugalmind-stalta` (mirrors AstaBench's pattern).
> - `scripts/build_plot_goldens.py` learns `--push` for DVC remote.
>
> **Acceptance**
> - Cloning the repo no longer downloads PNGs by default.
> - `dvc pull` (or `huggingface-cli download`) hydrates them.
>
> **Effort** M
> **Depends on** P3.2 (only worth it once the truth set is bigger)
> **Tracking** _(issue not yet filed)_

## P2.4 · Ship a real multi-step agent baseline

> **Goal** A ReAct-style baseline solver that has access to
> `python_session`, `fdsn_get_waveforms`, and `record(...)` as tools, so
> we can benchmark frontier coding agents not just frontier completion
> models.
>
> **Why** Everything we benchmark today assumes single-shot prompt →
> completion. AstaBench's `ReAct` and `smolagents` baselines are the
> reference comparison for code/data tasks; without one we can't claim
> our coding scores are real.
>
> **Deliverables**
> - `src/frugalmind/agents/react.py` (or InspectAI-native solver after P2.1).
> - Tool wrappers for FDSN fetch and the existing sandbox.
> - Documented baseline run in `notebooks/02_react_baseline.ipynb`.
>
> **Acceptance**
> - Baseline scores higher than `EchoAdapter` on every code/plot suite.
> - Baseline cost is reported alongside score.
>
> **Effort** L
> **Depends on** P2.1, P2.2
> **Tracking** _(issue not yet filed)_

## P2.5 · Align JSONLTelemetry with InspectAI's log format

> **Goal** Rename our telemetry fields to match Inspect's `.eval` schema
> where possible so `inspect view` works against our logs.
>
> **Why** Inspect's log viewer is the AstaBench-native way to debug a run.
> Our JSONLTelemetry is 80% there already.
>
> **Deliverables**
> - Field renames: `generation` → `output`, add `sample_id`, `run_id`.
> - Loader compatibility shim so old logs still load.
> - Documented field mapping in `docs/telemetry.md`.
>
> **Acceptance**
> - `inspect view results/*.jsonl` (or its successor) renders our logs.
> - `tests/test_telemetry.py` covers both old and new schema.
>
> **Effort** S
> **Depends on** P2.1
> **Tracking** _(issue not yet filed)_

---

# Phase 3 — Larger pivots

## P3.1 · Submit STA/LTA as an `inspect_evals` benchmark

> **Goal** Get the FrugalMind STA/LTA suite into the
> [`UKGovernmentBEIS/inspect_evals`](https://github.com/UKGovernmentBEIS/inspect_evals)
> registry so it sits next to DiscoveryBench, DS-1000, SUPER, CORE-Bench.
>
> **Why** `inspect_evals` is the AstaBench-recommended path for adding new
> benchmarks. Inclusion gives the seismology benchmark an order-of-magnitude
> larger audience and forces us to conform to a community-reviewed style.
>
> **Deliverables**
> - PR against `inspect_evals` adding `inspect_evals/frugalmind_stalta/`.
> - Migration guide from this repo's suites to the upstream layout.
> - Note in `README.md` that the canonical task definitions live upstream
>   once accepted.
>
> **Acceptance** PR merged. The suite runnable as
> `inspect eval inspect_evals/frugalmind_stalta_intent_extraction`.
>
> **Effort** L
> **Depends on** P2.1, P2.2, P2.5
> **Tracking** _(issue not yet filed)_

## P3.2 · Grow the truth set to 30–50 events

> **Goal** Add events covering volcanic LP, slow-slip / tremor, OBS
> microseism, induced seismicity, and a handful of additional regional and
> teleseismic events.
>
> **Why** Six events is too few for confidence intervals. AstaBench's
> DiscoveryBench has 264 problems. We don't need 264 to claim
> statistical traction, but 30–50 across more source classes is the floor.
>
> **Deliverables**
> - New event categories declared in `events.yaml`.
> - Each event verified against a citable catalog entry; remove all
>   `VERIFY` placeholders or convert them to verified entries.
> - Goldens regenerated for the expanded set.
>
> **Acceptance**
> - At least 30 events; at least 6 distinct categories.
> - No event has `catalog_id: TBD` in the public split.
>
> **Effort** L
> **Depends on** P2.1 (so the schema is settled before scaling)
> **Tracking** _(issue not yet filed)_

## P3.3 · Hidden test split via private HuggingFace dataset

> **Goal** Publish the full test split as a gated HuggingFace dataset,
> with leaderboard scoring done at submission time. Public repo carries
> only the validation split.
>
> **Why** Without a hidden test split, the benchmark contaminates as soon
> as someone trains on the prompts. AstaBench gates `allenai/asta-bench`
> on HuggingFace for exactly this reason.
>
> **Deliverables**
> - `your-org/frugalmind-stalta-test` HuggingFace dataset, gated.
> - Submission flow that runs the test scorer server-side.
> - Public leaderboard rows clearly tagged validation vs test.
>
> **Acceptance** A submission against test labels produces a score that
> the submitter can't reverse-engineer.
>
> **Effort** L
> **Depends on** P3.2 (need a real test set before this matters)
> **Tracking** _(issue not yet filed)_

## P3.4 · Skill-conditioned 3-axis leaderboard

> **Goal** Default leaderboard view becomes model × skill × score, with
> cost overlaid. Single-condition tables become a secondary view.
>
> **Why** AstaBench shows score and cost. FrugalMind's actually new axis
> is the skill. Featuring it as the default view is what makes us
> distinguishable rather than "another agent leaderboard."
>
> **Deliverables**
> - New chart on the static site (Chart.js): grouped bars per model,
>   one bar per skill condition.
> - Skill-lift table promoted above the per-row leaderboard.
> - Updated README screenshots.
>
> **Acceptance** A new visitor lands on the site and sees skill-lift
> first; cost-Pareto second; per-row third.
>
> **Effort** M
> **Depends on** P1.4
> **Tracking** _(issue not yet filed)_

## P3.5 · Per-suite RUBRIC.md documenting scorer rationale

> **Goal** Each suite ships a `RUBRIC.md` explaining what counts as a hit,
> why the lexical/code/SSIM thresholds are where they are, and what
> classes of failure they're designed to catch.
>
> **Why** AstaBench's recent E2E-Bench update post specifies why their
> scorer changed. Our scorers are codified but undocumented; readers
> can't tell whether a 0.7 is good or whether the scorer is too lenient.
>
> **Deliverables**
> - One `RUBRIC.md` per suite under `src/frugalmind_suites/sta_lta/`.
> - Rubric documents the threshold, the scoring formula, and at least
>   one worked positive and one worked negative example.
>
> **Acceptance** A reader who has never run the suite can read the
> rubric and predict, within ±10%, what score a given output will get.
>
> **Effort** M
> **Depends on** none
> **Tracking** _(issue not yet filed)_

---

# What we're NOT changing

These are FrugalMind's contributions and are explicitly out of scope for
the alignment work. They differentiate the project from AstaBench and
shouldn't be smoothed away in pursuit of standards conformance.

- **Skills system with three injection modes.** AstaBench has tools but no
  skill-conditioned scoring; the `none` / `instructions` / `full` lift is
  ours.
- **Parametric truth set.** events.yaml as the single source of truth, with
  five derived suites, is cleaner than DiscoveryBench's per-task hand
  authoring.
- **Frugality-first framing.** `FrugalRouter` + `BudgetGuard` +
  `LeaderboardRunner` together implement a "cheapest model that meets the
  floor" workflow, which is a different thesis from "rank by quality, show
  cost."
- **Negative-case discipline.** First-class no-event windows + the report
  scorer's `forbidden_terms` for hallucinated detections. AstaBench's
  data-analysis category doesn't have this baked in.
- **SSIM plot scoring.** Unusual, well-suited to scientific figures, and
  worth defending as a contribution rather than swapping for the standard
  exact-match scorer.

# How to add a new roadmap item

1. Open a PR against this file with a new `## Px.y · Title` section that
   uses the Goal/Why/Deliverables/Acceptance/Effort/Depends-on/Tracking
   format above.
2. Once merged, run `bash scripts/create_roadmap_issues.sh --only Px.y`
   to file the corresponding issue.
3. Update `Tracking` in this file with the issue link in a follow-up PR.
