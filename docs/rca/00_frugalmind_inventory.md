# What is already in `mdenolle/frugalmind` (inventory, 2026-09-14)

Source: local clone at `~/GitHub/frugalmind`, branch `main` at `8db9914`
("Bump codameter pin to v0.3.0"), in sync with `origin/main`; tags v0.1.0
through v0.4.0; last push 2026-08-04. 208 tracked files. No open PRs; open
issues are P2.3, P3.1 to P3.4 and six cost-axis proposals (#39 to #44).

Verification status of this inventory: everything marked "rerun" below was
executed today; everything else was read from files.

## Verified by rerunning

| Check | Result |
|---|---|
| `.venv/bin/python -m pytest` (Python 3.14.1, repo `.venv`) | 317 passed, 7 skipped, 10.1 s |
| `inspect_ai` in repo `.venv` or either pixi env | not installed (the `[eval]` extra is optional and was never installed here) |
| `inspect list tasks src/frugalmind_suites/sta_lta/inspect_tasks.py` in a scratch venv (Python 3.12, inspect_ai 0.3.263) | discovers all 5 STA/LTA tasks |
| `inspect eval <file>@task --model mockllm/model` by file path | fails: the suite modules use relative imports (`from .items import ...`) and Inspect's file loader cannot resolve them; programmatic `inspect_ai.eval(task())` on the installed package works |
| Docker daemon on this machine | binary present, daemon not running |

## Core package `src/frugalmind/` (10 modules, ~2,900 lines)

| Module | What it does |
|---|---|
| `__init__.py` | `TaskKind` enum (9 kinds), `DenolleGroupSuite` base (items + export_rows), `ModelCard`, `Generation`, `EvalResult`, `Adapter` protocol, `ModelRegistry`, `EvalRunner` |
| `adapters.py` | `EchoAdapter` (deterministic stub), `AnthropicAdapter`, `OpenAICompatAdapter` (OpenAI, Ollama, vLLM); stdlib urllib; token counts from provider response, cost = tokens x card rates |
| `budget.py` | `BudgetGuard`: per-model and total USD caps |
| `registry.py` | loads `config/models.yaml` into cards; tiers nano/small/medium/big/cloud |
| `router.py` | `FrugalRouter`: cheapest model above a quality floor, EMA score updates |
| `skills.py` | `SkillLoader` with injection modes none/instructions/full; manifest binds skills to suites |
| `telemetry.py` | `JSONLTelemetry` schema v2: `run_start` (run_id, task, task_args, solver, model), `sample` (id, epoch, output{text, model_id, prompt_tokens, output_tokens, latency_s, cost_usd}, score, skill_name, skill_mode, extra), `run_end`; v1 read shim |
| `export.py` | `BenchmarkRow` (id, dataset_id, suite_id, version, task_kind, split, visibility, prompt, gold, scorer_spec, metadata) to JSONL + `manifest.json` with sha256 per file |
| `leaderboard.py` | `LeaderboardRunner`: runs a suite under skill modes none/full, emits `SkillLiftRow` with score and cost |
| `cli.py` | `smoke-eval`, `export-leaderboard`, `run-ollama-intent`, `list-models`, `list-skills`, `run-skill-lift`, `export-suite` |

`src/frugalmind/agents/` (8 modules): a tool registry keyed by stable name;
Inspect `@tool`s `fdsn_get_waveforms` (ObsPy FDSN, runs in the harness
process in a worker thread), `python_session` (runs a snippet in the
sandbox), `record_submit`, `literature_search` (ranks a frozen JSON corpus
with the cutoff enforced inside the tool); `frugal_react` wraps Inspect's
`basic_agent` with a named tool bundle; `tool_use_stats` gives the
harness-competence axis (n_tool_calls, errors, submitted, converged);
`retrieval_leakage` audits submitted ids for post-cutoff or fabricated ids.

## Suites `src/frugalmind_suites/` (8 packages)

| Suite | Items | Gold source | Scorer | State |
|---|---|---|---|---|
| `sta_lta` | 6 events x 5 tasks (intent JSON, fetch code, trigger code, plot SSIM, report) | `events.yaml`; 2 validation/public, 4 test/private, 3 still flagged VERIFY | `json_extraction`, `code_execution` (staged 4 x 0.25), `plot_ssim`, lexical report with opt-in LLM-judge fallback | runs; public plot goldens were generated in synthetic mode |
| `synthetic_stalta` | 11 public cases from one Ridgecrest CI.MWC record via seeded transforms; hidden test split from a secret master seed | generator + secret | onset F1 within 1.5 s, staged 0.1/0.1/0.8 | live results on the site (E1 in the manuscript) |
| `pipeline_regression` | `pipelines.yaml` (seisbench, noisepy) | reference arrays | `numerical_regression` (pick_f1, allclose, pearson, rmse) with per-pipeline `sandbox_image` | scorer done; images not published |
| `dvv` | 10 cases per suite from codameter | codameter regenerates truth from a secret at score time (Mode A) | codameter scorers | runs in CI weekly (`dvv-suite.yml`) |
| `gaia_data_downloader` | 30 tasks synced from `uw-ssec/gaia-agentic-ai` issues (IRIS, USGS, NWIS, SNOTEL, ERA5, ...) | issue tracker; `expected_files` globs | `inspect_tasks.py` is a stub: every function raises `NotImplementedError` | not runnable |
| `lit_rag` | 3 seed tasks (`tasks.yaml`) + 12 known-item queries over a real arXiv physics.geo-ph corpus (`queries.yaml`) + 3 agentic queries over `ooi_corpus.json` | `ooi_corpus.json` is a placeholder: 10 synthetic abstracts with non-resolvable DOIs `10.0000/ooi-seed-*` | `retrieval_metrics` (recall@k, MRR, nDCG), `term_preservation`, `citation_support` | runs; OOI corpus must be replaced before any number is reported |
| `orchestration` | 1 seed task | reference DAG | `trajectory_dag` (node F1, edge F1, frugality), `trajectory_policy` | runs on the JSON-plan proxy; no subagents-as-tools solver |
| `paper_workflow` | `papers.yaml` + closed ontology of research operations | annotated DAGs | validated by script | annotation scaffold |

## Infrastructure

- Sandbox: `sta_lta/sandbox.py` runs host Python by default; `REPERE_USE_DOCKER_SANDBOX=1` switches to `ghcr.io/mdenolle/frugalmind-sandbox` (python 3.10-slim, numpy 1.26.4, scipy 1.13.1, matplotlib 3.9.2, scikit-image 0.24.0, obspy 1.4.1) with `--network=none`, non-root, tini. Network I/O is by design outside the sandbox: the `fdsn_get_waveforms` tool fetches in the harness process.
- CI: `evals.yml` (manual smoke), `pages.yml` (site deploy), `sandbox-image.yml` (GHCR build on tag/main), `sandbox-parity.yml` (host vs docker parity), `dvv-suite.yml` (weekly codameter run with the hidden secret). Recent runs green (2026-08-04).
- Site: static leaderboard with Chart.js Pareto scatter (`computeParetoFront` in `site/app.js`), openness and toolset pills, skill-lift table.
- Data policy docs: `docs/dataset_submission.md` (strict row schema, validation/test split, visibility, cutoff_date, canary string, rotation), `docs/golden_data_provisioning.md` (derive-from-secret vs host-gated), `docs/telemetry.md`, `docs/agentic_eval.md`, `docs/leaderboard_conditions.md`.
- Paper: `paper/manuscript.md` (Nature Machine Intelligence target) reports E1 (synthetic STA/LTA) and E2 (dv/v) on 4 local 7B models + claude-haiku, 410 calls, US$0.135; Methods states each configuration was run once and carries a TODO for n>=5 repeats with CIs.
- Skills: 8 under `.github/skills/` (stalta-detection, obspy-fdsn-fetch, seismic-plotting, seismic-report, seismo-data-agent, dvv-processing, literature-retrieval, research-orchestration) bound to suites by `manifest.yaml`.

## Gaps relative to this session's requirements (read, not rerun)

| Requirement | Present? | Note |
|---|---|---|
| Frozen price map with dates | partial | `config/models.yaml` has per-1k rates; only the three Anthropic cards carry `list_price_date` (2026-05-08); OpenAI cards undated; no Gemini, Kimi, Qwen-API, Mistral-API, Olmo-API entries; README says "13-model registry", file has 15 cards |
| Model-version pinning with unpinned flag | no | ids are whatever the provider accepts (`claude-sonnet-4-6`, `gpt-4o`, `olmo2:7b`); Inspect logs record the id sent, not the version returned; no flag |
| Repeated runs + reliability statistic | no | Inspect `epochs` unused; manuscript run once per configuration |
| Do-nothing baseline | partial | `EchoAdapter` and the `zero` scorer exist as harness checks, not as a reported leaderboard row |
| Lexical-retrieval-only baseline | no | no BM25 anywhere in the repo |
| Judge calibration / inter-rater agreement | no | judge fallback exists; `docs/lit_rag_scorers.md` lists judge reliability as design-only; sibling private repo `gaia-eval` has `runners/iaa.py` (Cohen's kappa + Jaccard) that could be lifted |
| Per-run full trace | partial | JSONL telemetry has tokens, cost, latency per sample; Inspect `.eval` logs (when tasks are run through Inspect) have the full message trace |
| Frozen DOI artifact per paper | no | `export.py` + `manifest.json` hashes exist; `CITATION.cff` exists; no Zenodo workflow, no separation between a paper's frozen submission bundle and the moving harness |
| OOI / RCA content | no | nothing OOI-specific beyond the placeholder corpus; no M2M, no OBS, no clock-drift task |
| Tier vocabulary | different | frugalmind uses a scorability spectrum T0 deterministic / T1 numerical / T2 perceptual / T3 trajectory / T4 rubric; this session's tiers are T1 physics / T2 execution / T3 reference / T4 judgment; a mapping is required |
