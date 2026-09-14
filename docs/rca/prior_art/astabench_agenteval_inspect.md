# Prior art for FrugalMind: AstaBench, agent-eval, Inspect AI

Report date: 2026-09-14. Everything below was read from cloned source at the commits listed, from the arXiv PDF text, or from the live Inspect docs. Items I could not confirm are tagged NOT VERIFIED. The caller asked for this as a file at `<scratch>/report_prior_asta_agenteval_inspect.md`; the agent harness blocked the write, so save this message there if the file is needed.

## 0. Identifier verification

| Item from the notes | Verdict | Evidence |
|---|---|---|
| arXiv:2510.21652 is the AstaBench paper | Correct | PDF v2 (21 Apr 2026), "AstaBench: Rigorous Benchmarking of AI Agents with a Scientific Research Suite", Bragg, D'Arcy, Balepur, Bareket, Dalvi et al., Ai2 Asta Team; published ICLR 2026 (OpenReview M7TNf5J26u). PDF at `scratchpad/prior/astabench_2510.21652.pdf`, text at `scratchpad/prior/astabench_paper.txt` (5861 lines) |
| github.com/allenai/asta-bench | Exists, Apache-2.0 | Cloned at `a9e338070fff` (2026-09-03, "Bump agent-eval to 0.1.54"). Package `astabench` 0.5.4 on PyPI (2026-06-17), Python >=3.11 |
| github.com/allenai/agent-eval | Exists | Cloned at `eadb6d23d04e` (2026-09-03, "Add DeepSeek V4 Pro preview pricing"). PyPI `agent-eval` 0.1.54 (2026-09-03), Python >=3.10 |
| github.com/UKGovernmentBEIS/inspect_ai | Exists | Sparse shallow clone at `ba57a753b23f` (2026-09-14). PyPI `inspect-ai` 0.3.263 (uploaded 2026-09-04), Python >=3.10. CHANGELOG header "0.3.263 (03 September 2026)" plus an "Unreleased" section |
| inspect.aisi.org.uk | Correct docs host | asta-bench README still links the older `inspect.ai-safety-institute.org.uk`, same docs |
| Leaderboard web app | Exists, not in the notes | github.com/allenai/asta-bench-leaderboard at `23c11df53f3f` (2026-08-11); HF Space `allenai/asta-bench-leaderboard` (docker SDK) |
| litellm price-map pin | Verified | agent-eval pins the map at commit `9c117a58be8fb8066e833aa92dd98fdf15771e50`; GitHub API confirms that is the `v1.88.1` tag |
| HF data | Verified | `allenai/asta-bench` gated ("auto"), last modified 2025-08-26, pinned in code at revision `a600dc767f850385f4664772e3ba7a7f8be17d5e`; `allenai/asta-bench-results` public, last modified 2026-09-04 |

Clones live under `<scratch>/prior/` (abbreviated `prior/` below).

## 1. AstaBench (allenai/asta-bench + paper)

Headline: AstaBench is a thin layer over Inspect. The suite is a YAML file naming Inspect tasks, the cost accounting and leaderboard live entirely in agent-eval, and the date restriction is enforced by wrapping tool calls in the task setup, not by the harness. There is no repeated-run machinery anywhere in the repo.

### 1a. Time-invariant cost accounting

Where it lives: not in asta-bench. `prior/asta-bench/astabench/cli.py` re-exports agent-eval's `eval` and `score` commands with the config path defaulted to `astabench/config/v1.0.0.yml` and `--split` restricted to `validation|test`. Everything cost-related is in agent-eval (Section 2). The only asta-bench contribution is `prior/asta-bench/astabench/util/model.py`, which lets agents that call models outside Inspect inject a `ModelEvent` with a `ModelUsage` (`record_model_usage_with_inspect`), normalising bare model names to `provider/model` via `litellm.get_llm_provider`, and validating token-count consistency (`total_tokens` <= sum of components, >= max(input, output)).

Frozen price map, exactly:

| Aspect | Value | File |
|---|---|---|
| Source | litellm `model_prices_and_context_window_backup.json` fetched from a pinned GitHub commit URL at score time | `prior/agent-eval/src/agenteval/cli.py` `prep_litellm_cost_map()` lines 65-109 |
| Pin | commit `9c117a58...` = litellm v1.88.1; `pyproject.toml` pins `litellm>=1.67.4.post1,<=1.88.1` | same, plus `Development.md` "Bumping litellm" |
| Guard | refuses to score unless `LITELLM_LOCAL_MODEL_COST_MAP=True` (so litellm never pulls a live map); warns if the installed litellm knows models absent from the pinned map; prints sha256 of the registered map and litellm version | same |
| Provenance in output | `TaskResults.cost_map_url` written into `scores.json` ("Points to a specific git commit so the cost basis is exactly reproducible") | `prior/agent-eval/src/agenteval/score.py` line 227 |
| Overrides | `CUSTOM_PRICING: dict[str, litellm CostPerToken]` (fields `input_cost_per_token`, `output_cost_per_token`, per token not per million) and `CUSTOM_PRICING_WITH_CACHE: dict[str, CostPerTokenWithCache]` adding `cache_read_input_token_cost`, `cache_write_input_token_cost: float \| None` | `prior/agent-eval/src/agenteval/local_cost.py` |
| Key | the model string as it appears in the Inspect log `ModelEvent.output.model`, which is why both `claude-3-5-haiku-20241022` and `anthropic/claude-3-5-haiku-20241022` are listed | same, comment "key represents model name as found in inspect model_usage" |
| Name translation | `MODEL_TRANSLATIONS` maps log names to litellm names (e.g. `models/gemini-2.5-pro-preview-06-05` -> `gemini/gemini-2.5-pro`) | `prior/agent-eval/src/agenteval/log.py` lines 22-28 |

How dates and versions are handled: there is no date axis in the map. Versioning is by pinning the litellm commit; a price change is handled by either bumping the pin and rescoring everything (paper footnote 10: "the cost map snapshot used for the leaderboard may be periodically updated, but we will always re-calculate all costs based on the current snapshot"), or by adding a hand-entered historical price with a link to the old litellm commit (the `deepseek/deepseek-v4pro-preview` entry, priced "before the GA pricing change took effect on 2026-08-16 at 16:00 UTC"). Model snapshot dates are reflected only through the model id string itself; the leaderboard marks ids without a date stamp as "(unpinned)" in `prior/agent-eval/src/agenteval/leaderboard/model_name_mapping.py` and the paper marks them with a dagger.

Cost formula (`log.py` `compute_model_cost`, lines 96-205): per ModelEvent, branch on (1) `CUSTOM_PRICING` -> `litellm.cost_per_token(custom_cost_per_token=...)`; (2) `CUSTOM_PRICING_WITH_CACHE` -> manual arithmetic with cache read/write; (3) otherwise reconstruct a litellm `Usage` object by detecting the provider's token convention from the arithmetic identity (`input == total - output` for OpenAI style; `input == total - output - reasoning` for Gemini; `input == total - output - cache_read - cache_write` for Anthropic) and call `cost_per_token(usage_object=...)`. Any exception (unknown model, unrecognised token pattern) sets the sample's cost to `None`, logs a warning, and stops accumulating for that sample.

Unknown models: a `None` sample cost propagates upward. `summary.py` `_safe_mean` returns `None` for the task cost if any sample is `None`; `leaderboard/upload.py` `compress_model_usages` nulls the whole `model_costs` list when any entry is `None`; the plot code places such agents as hollow markers to the right of a dashed divider only when `--scatter-show-missing-cost` is passed, otherwise they are absent from the cost axis. asta-bench `CHANGELOG.md` 0.5.4 records the failure mode: litellm resolves the provider from the installed litellm's registry, not from the registered map, so an unknown model raises "LLM Provider NOT provided" and "nulls the entire task cost"; both pins must move together.

Judge cost exclusion: `log.py` `collect_model_usage` walks the sample's event tree and drops `ModelEvent`s whose innermost span contains a `ScoreEvent` (or legacy `StepEvent(type="scorer")`), so LLM-judge tokens are not billed to the agent.

Paper text (Sec. 4.2): "we use a frozen snapshot of the litellm cost map ... It factors in cache discounts ... however, it does not factor in any latency-related discounts (e.g., service tier or batching). Using a frozen snapshot allows a fair comparison of evaluation costs even if API prices change between evaluations." Footnote 9: custom models priced from Together AI size-based pricing.

### 1b. Date-restricted corpus tools

Which tools. Two generations coexist in `prior/asta-bench/astabench/tools/`:

| Tool set | Backend | Date mechanism | File |
|---|---|---|---|
| `paper_search`, `snippet_search` (legacy) | Semantic Scholar Graph API `https://api.semanticscholar.org/graph/v1/` with `ASTA_TOOL_KEY` | `snippet/search` supports `insertedBefore` natively; `paper/search` does not, so the code passes `publicationDateOrYear=:YYYY-MM-DD` and comments that publication date is "an approximation" of insertion date | `search.py` lines 144-186 |
| Asta MCP tools: `snippet_search`, `search_papers_by_relevance`, `get_paper`, `get_paper_batch`, `get_citations`, `search_authors_by_name`, `get_author_papers`, `search_paper_by_title` | Ai2's "Asta Scientific Corpus" served over MCP at `https://asta-tools.allen.ai/mcp/v1` (closed server; internals NOT VERIFIED) | see below | `asta_tools.py` `async_make_asta_mcp_tools(insertion_date=...)` lines 655-779 |
| Provider-native web search (`make_native_search_tools`) | OpenAI, Anthropic, Gemini, Perplexity built-in search | only Perplexity honours a cutoff (`search_before_date_filter`); the other three get no restriction | `native_provider_tools.py` lines 40-78 |

How the cutoff is enforced for the MCP tools (all client-side, wrapping the `ToolDef`):

1. Argument override: if the MCP tool exposes `inserted_before`, it is forced to the task's date and removed from the schema the LLM sees (`make_override_wrapper`, `arg_overrides`, with the parameter's docstring block stripped so the model cannot discover it). Tools exposing `publication_date_range` instead get `:YYYY-MM-DD` (last second before the cutoff).
2. Post-hoc subfield filter: `citations` and `papers` subfields in responses are pruned of papers whose `publicationDate` (or `year`, taken as Dec 31) is after the cutoff; the required date fields are injected into the `fields` request and removed again from the response (`_wrap_subfield_date_filter`).
3. Hard error on direct lookups: `get_paper` and `get_paper_batch` raise `ToolError("Paper X is newer than the date cutoff of ... and is not allowed to be requested")` so a model cannot fetch a known-new paper by id (`_wrap_toplevel_date_filter`).
4. Retry wrapper on 429/529/504 with exponential backoff (max 10 retries, 60 s cap).

Where the date comes from: a per-task constant in task code, not a per-run flag and not a dataset field originally. `set_insertion_date(dataset, date)` in `prior/asta-bench/astabench/util/sample.py` copies it into every `sample.metadata["insertion_date"]` so non-MCP agents (for example CLI coding agents that read env vars before launching) can mirror it. Values at HEAD:

| Task | Constant | Value at HEAD | Paper Table 2 |
|---|---|---|---|
| LitQA2-FullText / -Search | `INSERTED_BEFORE` in `evals/labbench/litqa2/task.py` line 41 | `2024-10-17` | 2024-10-17 |
| ScholarQA-CS2 | literal in `evals/sqa/task.py` lines 492-501 (only for `split in {"dev","test"}`) | `2025-05` | 2025-05-01 |
| PaperFindingBench | `PF_INSERTED_BEFORE` in `evals/paper_finder/paper_finder_utils.py` line 22 | `date(2025, 6, 1)` | 2025-06-01 |
| ArxivDIGESTables | `INSERTED_BEFORE` in `evals/arxivdigestables/task.py` line 26 | `2026-01-01` | "Paper IDs" (snippet search restricted to given ids) |

The scorer double-checks in PaperFindingBench: `check_verified` (`paper_finder_utils.py` lines 116-140) re-queries S2 for the publication dates of every returned corpus id and splits results into valid-and-dated, valid-but-undated/late, and unknown ids; only 250 results are considered "to prevent brute force".

Justification against contamination, verbatim from the paper: Sec. 4.1 "These tools can restrict outputs to papers preceding a date; AstaBench uses this feature to limit results to the date of benchmark creation so that new papers do not contaminate results"; Table 2 caption "restrict to papers before the specified 'Date Cutoff' (exclusive). (Original datasets were filtered to ensure questions are answerable with the environment.)"; Appendix A principle 2 "benchmark suites provide standard search tools with reproducible test-time access to the same document corpus"; Reproducibility Statement "date-restricted access to the supporting document corpus". This targets corpus drift (rubric validity as new papers appear), not model training-set contamination; the paper defers the latter to future work ("fresh benchmark problems ... past the training cut-off date of models"). The code concedes the approximation: `filter_papers` docstring "the actual date returned is the *publication* date, which may be different than the date the paper was inserted into the corpus".

Tool precedence: `merge_tools_with_state` (`prior/asta-bench/astabench/util/state.py`) keeps the task-provided (date-restricted) tool when a solver supplies a tool of the same name, unless `prefer_given_tools=True`.

### 1c. Openness and tooling classifications

Canonical strings (`prior/agent-eval/src/agenteval/config.py` lines 11-19, with the comment that the leaderboard expects exactly these or a listed alias):

| Dimension | CLI alias | Canonical string | Definition (paper App. B, README) |
|---|---|---|---|
| Openness | `ow` | `Open source & open weights` | "Both agent code and ML model weights are publicly available, enabling full end-to-end reproducibility" |
| Openness | `os` | `Open source & closed weights` | "Agent code is available but relies on proprietary ML models, allowing partial reproducibility of the approach" |
| Openness | `api` | `Closed source & API available` | "Implementation details are proprietary, but the system is accessible via API, enabling result verification but not method reproduction" |
| Openness | `c` | `Closed source & UI only` | "Neither code nor programmatic API access is available" |
| Tooling | `s` | `Standard` | "Uses only predefined tools from the evaluation environment (as defined in Inspect's state.tools)" |
| Tooling | `ci` | `Custom interface` | "Uses custom tools for accessing an equivalent underlying environment": literature tasks "limited to date-restricted usage of the Asta Scientific Corpus"; code tasks "limited to an IPython shell in a machine environment initialized with the standard Asta Environment sandbox Dockerfile (or equivalent)" |
| Tooling | `c` | `Fully custom` | "Uses tools beyond constraints of Standard or Custom interface" |

The web app accepts legacy aliases ("Open Source + Open Weights", "Open Source", "API Available", "Closed", "Custom with Standard Search") in `prior/asta-bench-leaderboard/aliases.py`, colours markers by openness and shapes them by tooling (`leaderboard_transformer.py` lines 368-395). Paper Table 3 shows the classification is per agent class, and openness "applies to the agent (including the model used)": ReAct is the only "Standard" general agent; all Asta specialised agents are "Custom interface" or "Fully custom".

### 1d. Pareto score-vs-cost reporting

Computed in two places with the same rule:

- `prior/agent-eval/src/agenteval/leaderboard/view.py` `_get_frontier_indices` (lines 1173-1201): sort by (cost asc, score desc); keep a point iff its score strictly exceeds the running max. Marks `overall/frontier`, `tag/<t>/frontier` boolean columns in the exported table.
- `prior/asta-bench-leaderboard/leaderboard_transformer.py` lines 465-495 and `get_pareto_df` lines 710-745: same sweep but grouped by equal cost so co-optimal ties both stay; drawn as a dashed "Efficiency Frontier" line in plotly; frontier agents get a trophy and green name.

What is plotted: x = mean cost per problem in USD (`overall/cost`, `tag/<t>/cost`, `task/<t>/cost`), y = the primary score; one subplot per tag or per task; log-x is optional in the CLI (`--scatter-x-log-scale`) and used in the paper's Figure 2 ("x-axis (cost per answer in dollars) uses a log scale"). CLI writes `data.jsonl` plus `bar.png`, `scatter.png`, `scatter_<name>.png`.

Variance and CI: 95% CI half-width = 1.96 x stderr, computed only at task level (`view.py` lines 585-600: `task/<t>/score_ci`, `task/<t>/cost_ci`); tag and overall rows have `score_stderr=None`, `cost_stderr=None` in `summary.py` lines 147-168. Score stderr is whatever Inspect metric named `{scorer}/stderr` the task emitted (across samples, one run); cost stderr is `stdev(per-sample costs)/sqrt(n)`. Error bars are drawn on both axes when present (`_plot_error_bars`). The paper's Appendix D states category SEs are propagated as sqrt(sum w_i^2 SE_i^2)/sum w_i assuming task independence; that propagation is NOT in agent-eval or the leaderboard app at these commits (NOT VERIFIED where it was computed for the paper). Repeated-run variance is not measured: one log per task per submission (see 1e).

### 1e. Task format, splits, repeated runs

Format: plain Inspect `@task` functions registered under the `astabench/` namespace by the `[project.entry-points.inspect_ai] astabench = "astabench.evals._registry"` entry point (`prior/asta-bench/pyproject.toml` line 80; registry at `astabench/evals/_registry.py`). Tasks ship a `setup=` solver chain that injects the restricted tools with `use_tools(...)`, a `not_implemented_solver()` placeholder so the user must pass `--solver`, and the scorer(s). Example: `astabench/evals/sqa/task.py` lines 466-540 (`fail_on_error=False`, LLM judge `google/gemini-3-flash-preview`, temperature 0.5, top_p 0.95).

Splits: separate task functions per split (`*_validation`, `*_test`; SQA uses `sqa_dev`) because "there is no way to pass task-arguments to the underlying `inspect eval-set`" (`INTERNAL.md`). The suite YAML `prior/asta-bench/astabench/config/v1.0.0.yml` lists 11 validation and 11 test tasks with `primary_metric` in the form `{scorer}/{metric}` (e.g. `score_paper_finder/adjusted_f1_micro_avg`, `is_correct/accuracy`, `global_avg/mean`), one tag each (`lit`, `code`, `data`, `discovery`), and `macro_average_weight_adjustments` giving the two LitQA2 tasks weight 0.5. Test data is held out only by gating: `allenai/asta-bench` on HF is gated, pinned by `ASTA_BENCH_DATASET_REPO = "allenai/asta-bench"` and `ASTA_BENCH_DATASET_REVISION = "a600dc767f850385f4664772e3ba7a7f8be17d5e"` in `astabench/constants.py`, and loaded with `HF_TOKEN`. No hidden test set.

Repeated runs: no `epochs` anywhere under `astabench/evals`. `agenteval.score.process_eval_logs` raises "Task X already read" if a log directory holds two logs for one task, so a submission is exactly one run per task; duplicates are archived by `scripts/dedupe_eval_logs.py` or `--duplicate-task-policy keep-latest` in the rescoring script. Variance is therefore across samples only. `scripts/eval_then_score.sh` splits solve (`--no-score --log-format json`) from a frozen scorer environment (`solvers/scorer/pyproject.toml`, `inspect-ai==0.3.203`) and `INTERNAL.md` documents rescoring when a judge model retires. `eval_config.json` must be byte-identical on rerun into the same log dir.

### 1f. Leaderboard submission flow and bundle contents

Flow (README "Submitting to the Leaderboard", `INTERNAL.md`, `agent-eval/src/agenteval/cli.py`):

1. `astabench eval --solver ... --model ... --split test --log-dir D` wraps `inspect eval-set`, refuses to run on a dirty tree or an unpushed commit (`verify_git_reproducibility` in `agent-eval/src/agenteval/io.py`; `--ignore-git` bypasses), and writes `D/eval_config.json`.
2. `astabench score D` (Section 1a) writes `D/scores.json` and `D/summary_stats.json`.
3. Public: `tar czfv name.tar.gz D` and upload through the HF Space form with agent name, description, openness, tooling. Internal: `astabench publish D --openness ow --tool-usage s --agent-name ...` uploads the folder to `hf://datasets/<submissions-repo>/{config_version}/{split}/{username}_{agent}_{YYYY-MM-DDTHH-MM-SS}/` and writes `submission.json`; `astabench score hf://...` writes `summaries/<path>/scores.json`; `astabench lb publish hf://... --repo-id <results-repo>` assembles one JSON row.

Bundle contents:

| File | Schema | Defined in |
|---|---|---|
| `*.eval` (one per task) | Inspect log | Inspect |
| `eval_config.json` | `EvalConfig{suite_config: SuiteConfig, split: str, inspect_command: list[str]}` | `agent-eval/src/agenteval/models.py` |
| `submission.json` | `SubmissionMetadata{submit_time, username, agent_name, agent_description, agent_url, logs_url, logs_url_public, summary_url, openness, tool_usage}` | same |
| `scores.json` | `TaskResults{results: [TaskResult{task_name, eval_spec{solver, solver_args, model, model_args, task_args, revision{type,origin,commit,dirty}, packages}, metrics: [{name, value}], model_usages: [[{model, usage: ModelUsage}]] per sample, model_costs: [float\|None] per sample}], cost_map_url}` | `agent-eval/src/agenteval/score.py` |
| `summary_stats.json` | `{stats: {"overall", "tag/<t>", "task/<t>": {score, score_stderr, cost, cost_stderr}}}` | `agent-eval/src/agenteval/summary.py` |
| Results-repo row | `LeaderboardSubmission{suite_config, split, results, submission}`; Arrow schema in `leaderboard/dataset_features.yml` (dict fields JSON-stringified; `model_usages` compressed to one entry per model per sample) | `agent-eval/src/agenteval/leaderboard/` |

Score-time warnings: more than one (solver, solver_args, model, model_args) spec in one directory; more than one (revision, packages); any task args passed by the user ("For fair comparison, do not override the task arg defaults"); missing tasks.

### Design constraints implied for FrugalMind (from AstaBench)

1. Keep the price map outside the harness that runs the agent, key it by the exact model string the provider returns in the log, and store the map's content hash and source URL/commit in every scored output (`cost_map_url` pattern). Rescore all historical logs whenever the map changes rather than mixing maps.
2. Give the price map a date dimension. AstaBench has none and had to hand-patch the DeepSeek preview price with a commit link; FrugalMind runs over months on live APIs, so store `(model_id, valid_from, valid_to, input, output, cache_read, cache_write)` and pick the row by run date, with the frozen-snapshot policy applied per leaderboard version.
3. Treat an unknown model as a hard scoring failure with a named cause, but do not silently null the whole task the way `compute_model_cost` does; emit per-sample `cost=None` plus a `cost_missing_reason` so the Pareto plot can show the point as "no cost" instead of dropping it.
4. Exclude judge-model tokens from agent cost by span, not by model name (the `ScoreEvent`-span rule), because FrugalMind's RAG judges may share a model with the agent.
5. Enforce the corpus cutoff in three layers like `asta_tools.py`: force and hide the date argument, filter nested results post hoc, and error on direct id fetches past the cutoff. For OOI/EarthScope live data the analogue is a request-time filter on `start`/`end` and on metadata ingestion timestamps, plus a scorer-side re-check of every returned record's date (the `check_verified` pattern).
6. Put the cutoff in `sample.metadata["insertion_date"]` (or `corpus_snapshot`) so agents running in a sandbox without the harness's tool wrappers can read it; AstaBench added this after the fact for CLI coding agents.
7. Expect provider-native search to be unrestrictable (only Perplexity accepts a date filter); either ban native search in the "Standard" tooling class or classify it as "Fully custom".
8. Use two coordinates for every submission, openness and tooling, with the exact four plus three canonical strings above if you want cross-leaderboard comparability, and record "(unpinned)" for any model id without a date stamp.
9. Separate solve from score with an independently pinned scorer environment, so judge-model retirement or a new price map can be replayed over old `.eval` files without re-running agents.
10. AstaBench's CI is across samples within one run; FrugalMind's stated goal (variance across repeats) is not covered by this prior art and must be added via Inspect epochs (Section 3).

### What FrugalMind could adopt directly vs must build (AstaBench)

Adopt directly: the suite YAML shape (`name`, `version`, `splits[].tasks[]{name, path, primary_metric, tags}`, `macro_average_weight_adjustments`); the `{scorer}/{metric}` primary-metric convention with a sibling `{scorer}/stderr`; `merge_tools_with_state` (prefer task tools on name clash); `set_insertion_date`; the tool-wrapping trio in `asta_tools.py` as a template for any MCP-served tool; `record_model_usage_with_inspect` for agents that bypass Inspect's model API; the openness/tooling vocabulary; the git-clean check.

Must build: a dated price map (AstaBench's is undated); network-restricted sandbox policy for live REST APIs (AstaBench restricts search results, not egress); a "corpus snapshot id" per run for a drifting paper index (AstaBench's snapshot is a single date constant per task); repeated-run aggregation and variance reporting; Pareto plots with CI on both axes at the aggregate level (AstaBench only has task-level CI); any scorer for numeric sensor-data outputs (AstaBench has none; nearest is DiscoveryBench's LLM rubric and SUPER's trajectory checks).

## 2. agent-eval (allenai/agent-eval)

What it is: a small Python library plus a click CLI `agenteval` (`prior/agent-eval/src/agenteval/cli.py`, 1068 lines) with subcommands `eval`, `score`, `publish`, `backfill`, `lb publish`, `lb view`. Modules: `config.py` (suite schema), `models.py` (EvalConfig, SubmissionMetadata), `score.py` (log -> TaskResult), `log.py` (usage collection and cost), `summary.py` (aggregation), `local_cost.py` (overrides), `leaderboard/{models,upload,view,schema_generator,model_name_mapping}.py`. 0.1.54; Python >=3.10.

How it wraps Inspect: by subprocess, not API. `agenteval eval --config-path C --split S [inspect args] LOG_DIR` builds `["inspect", "eval-set", *args, "--log-dir", LOG_DIR, "--display", "plain", *task_paths]` and `Popen`s it (cli.py lines 987-1056, with Ctrl-C handling that waits for sandbox cleanup). Scoring reads logs through `inspect_ai.log.list_eval_logs`, `read_eval_log(..., header_only=True)` and `read_eval_log_samples(..., all_samples_required=True)`. `inspect-ai` is deliberately absent from base dependencies; the `scoring` extra pins `inspect-ai==0.3.203` and `leaderboard` adds seaborn/matplotlib/pandas. Task identity is resolved from `EvalLog.eval.task_registry_name` matched against the suite's `path`, with suffix matching (`super_test` matches `astabench/super_test`) and a fallback to the last path segment.

Log schema it produces: the four JSON files in Section 1f. The README still says results go to `agenteval.json`; that is the legacy single-file format that `agenteval backfill` converts, so the README is stale relative to the code.

Cost computation: Section 1a in full. Per-sample cost list, per-task mean and stderr, tag/overall weighted means of task costs.

Aggregate statistics (`summary.py`): task score = primary metric value from the Inspect log; task stderr = the Inspect metric named `{scorer_of_primary}/stderr` (missing -> `None` with a warning); task cost = mean of non-None sample costs (`None` if any sample is None); cost stderr = sample stdev / sqrt(n) (`None` if n < 2 or any None); tag = weighted arithmetic mean over tasks with missing scores replaced by 0 unless `preserve_none_scores`; overall = unweighted mean over tags; no bootstrap, no CI computed here. The viewer multiplies task stderr by 1.96. Number of repeats: 1; nothing in the code averages across runs.

Leaderboard/HF integration: two HF dataset repos (submissions: raw logs + config; results: one JSON per submission under `{config}/{split}/*.json`), the results README carrying a `configs:` block with `features` from `dataset_features.yml` and `data_files` per split, validated at publish time (`Readme.download_and_parse`, `schema_generator.load_dataset_features`; publish exits if the schema or config/split is missing). `lb view --repo-id --config --split [--tag] [--save-dir]` loads via `datasets.load_dataset`, builds display names `agent (model1, model2)` ordered by token share, handles duplicate names (`--dedup index|latest`), appends `(reasoning_effort=...)` when `model_args` says so, derives a `source_url` of the form `origin/tree/commit` from `EvalRevision`, and drops known agents with incomplete usage info (Elicit, SciSpace, You.com).

### Design constraints implied for FrugalMind (from agent-eval)

1. Keep the harness's scoring package inspect-free at the base level and pin Inspect only in the scorer extra; AstaBench needed this so solvers and scorer could run different Inspect versions.
2. Write cost per sample as an explicit list next to per-sample usage, never only an aggregate; that is what makes rescoring and per-sample Pareto points possible.
3. Store per-sample usage per model (`model_usages[sample][model]`) and compress only at publish time; keep the raw form in the submission tree.
4. Reuse the four-file bundle layout but add `repeats` (or `epochs`) to `EvalConfig` and a `run_index` to each `TaskResult`, since agent-eval assumes one log per task.
5. Adopt the suffix-tolerant task-name resolution and the "already read" error; both catch mis-assembled bundles early.
6. Add a stderr source policy: agent-eval assumes each scorer emits a `stderr` metric and warns otherwise; FrugalMind should compute it centrally from per-sample scores read from the log rather than trusting the task author.
7. Add cost CI at tag and overall level (agent-eval leaves them `None`).
8. Expect HF `datasets` schema rigidity: dict-valued fields must be JSON strings (`_EVALSPEC_JSON_FIELDS`), and every config version must share one Arrow schema.

### What FrugalMind could adopt directly vs must build (agent-eval)

Adopt directly (pip-installable): `SuiteConfig`/`Split`/`Task` pydantic models; `collect_model_usage` (judge-span exclusion); the token-convention detection in `compute_model_cost`; `process_eval_logs`; `compute_summary_statistics` with tag weights; `_get_frontier_indices`; the HF upload/README-schema tooling if you want an HF-hosted leaderboard.

Must build: a dated, hash-pinned price map that does not go through litellm's provider resolution (the 0.5.4 CHANGELOG failure shows litellm's installed registry is a hidden dependency); repeat-aware aggregation (mean of per-run means, between-run SD, or Inspect epochs reducers); a Pareto routine that carries CI on both axes and reports the frontier with uncertainty (e.g. bootstrap over samples and repeats); per-sample plots (agent-eval plots only aggregates).

## 3. Inspect AI (UKGovernmentBEIS/inspect_ai, docs at inspect.aisi.org.uk)

Version: 0.3.263 on PyPI (2026-09-04), CHANGELOG "0.3.263 (03 September 2026)", version derived by `setuptools_scm` from git tags matching `[0-9]*.[0-9]*.[0-9]*`. Python `>=3.10`. Repo HEAD read at `ba57a753b23f` (2026-09-14) with an "Unreleased" section, so the source I quote is slightly ahead of 0.3.263. agent-eval scoring pins 0.3.203 and asta-bench solve requires `>=0.3.233,<0.3.259` (OpenAI SDK 3.x conflict with litellm), so version drift between the three is already a live issue.

### Tasks, datasets, solvers, scorers

`Task(dataset, solver, scorer, epochs, sandbox, config, model, model_roles, message_limit, token_limit, turn_limit, time_limit, working_limit, cost_limit, approval, review, name, display_name, version, metadata, tags, setup, cleanup, metrics, ...)` (docs tasks.html; `eval()` signature in `prior/inspect_ai/src/inspect_ai/_eval/eval.py` lines 126-212). `Task.version: int | str` is recorded as `EvalSpec.task_version`. Task parameters are the `@task` function's arguments, set with `-T key=value`.

`Sample(input, target, id, choices, metadata, files, setup, sandbox)`; files map target paths to inline text, paths or data URIs; `setup` is a bash script run in the sandbox. Datasets: `json_dataset`, `csv_dataset`, `hf_dataset`, `MemoryDataset` (AstaBench uses `MemoryDataset` built from HF-downloaded JSON).

Solver protocol `async def solve(state: TaskState, generate: Generate) -> TaskState`, registered with `@solver`, composed with `chain(...)`; built-ins `generate`, `use_tools`, `system_message`, `prompt_template`, `user_message`, `chain_of_thought`, `self_critique`, `multiple_choice`; agents via `react()` and `bridge()` (agent-bridge patches an OpenAI-compatible client so third-party agents' calls are logged). `TaskState` exposes `messages`, `output`, `tools`, `metadata`, `store`, `completed`, `epoch`, `sample_id`, `model`.

Scorers return `Score(value, answer, explanation, metadata)`; built-ins `includes`, `match`, `pattern`, `answer`, `exact`, `choice`, `f1`, `model_graded_qa`, `model_graded_fact`, `math`. Metrics (docs metrics.html): `accuracy`, `mean`, `std`, `var`, `stderr(cluster=...)`, `bootstrap_stderr`, `ci` (mapping with `lower`/`upper`), `ci_wilson`, `frequency`, `categorical`, `krippendorff_alpha`, `grouped(metric, key)`, `aggregate`. Clustered stderr requires every sample to carry the cluster key in metadata (`_metrics/std.py` lines 57-100, finite-cluster correction). Custom metrics can declare `scores="unreduced"` to see per-epoch scores.

### Epochs and reducers

`epochs: int | Epochs(count, reducer)` where reducer is a name or list of names; multiple reducers produce one `EvalScore` per reducer (`EvalScore.reducer: str | None`). Registered reducers in `prior/inspect_ai/src/inspect_ai/scorer/_reducer/reducer.py`: `mode`, `majority`, `mean`, `median`, `at_least_{k}`, `pass_at_{k}`, `pass_k_{k}`, `max`, `collect` (keeps the list of per-epoch values). `EvalConfig.epochs` and `epochs_reducer: list[str]` are stored in the log; `EvalSample.epoch: int` tags each repeat; `EvalLog.reductions: list[EvalSampleReductions]` holds per-sample reduced scores; `EvalResults.total_samples` = dataset x epochs.

### Eval logs

Formats: `.eval` (default since v0.3.46; a zip whose members are `header.json`, per-sample JSON entries, `summaries.json`, `reductions.json` and a `_journal/` for in-progress writes, per `log/_recorders/eval.py` lines 111-120) and `.json`. Select with `--log-format eval|json` or `INSPECT_LOG_FORMAT`; `--log-dir` / `INSPECT_LOG_DIR`. API: `read_eval_log(path, header_only=)`, `read_eval_log_samples()` (generator), `read_eval_log_sample()`, `read_eval_log_sample_summaries()`, `list_eval_logs()`, `write_eval_log()`; CLI `inspect log list|dump|convert|export-config|schema`.

Fields that matter for FrugalMind (from `prior/inspect_ai/src/inspect_ai/log/_log.py`):

| Object | Fields |
|---|---|
| `EvalLog` | `version`, `status`, `eval: EvalSpec`, `plan`, `results`, `stats`, `error`, `invalidated`, `log_updates`, `config_updates`, `tags`, `metadata`, `samples`, `reductions`, `location`, `etag` |
| `EvalSpec` | `eval_set_id`, `eval_id`, `run_id`, `created`, `task`, `task_id`, `task_version`, `task_file`, `task_registry_name`, `task_attribs`, `task_args`, `task_args_passed`, `solver`, `solver_args`, `solver_args_passed`, `tags`, `dataset: EvalDataset{name, location, samples, sample_ids, shuffled}`, `sandbox`, `model`, `model_generate_config`, `model_base_url`, `model_args`, `model_roles`, `config: EvalConfig`, `revision: EvalRevision{type="git", origin, commit, dirty}`, `packages: dict[str,str]`, `metadata`, `scorers`, `metrics`, `headline_metric` |
| `EvalConfig` | `limit`, `sample_id`, `sample_shuffle`, `epochs`, `epochs_reducer`, `approval`, `review`, `fail_on_error`, `continue_on_fail`, `retry_on_error`, `score_on_error`, `message_limit`, `token_limit`, `token_limit_type`, `turn_limit`, `time_limit`, `working_limit`, `cost_limit`, `max_samples`, `max_tasks`, `max_subprocesses`, `max_sandboxes`, `sandbox_cleanup`, `sandbox_prebuilt`, `log_samples`, ... |
| `EvalSample` | `id`, `epoch`, `input`, `choices`, `target`, `sandbox`, `files`, `setup`, `messages`, `output: ModelOutput`, `scores: dict[str, Score]`, `metadata`, `store`, `events`, `timelines`, `model_usage: dict[str, ModelUsage]`, `role_usage`, `model_fallbacks`, `started_at`, `completed_at`, `total_time`, `working_time`, `uuid`, `invalidation`, `error`, `error_retries`, `attachments` |
| `EvalStats` | `started_at`, `completed_at`, `model_usage: dict[str, ModelUsage]`, `role_usage`, `connection_limit_history` |
| `EvalResults` / `EvalScore` / `EvalMetric` | `total_samples`, `completed_samples`, `scores: [EvalScore{name, scorer, reducer, scored_samples, unscored_samples, params, metrics: {name: EvalMetric{name, group, value, params, metadata}}}]`, `headline`, `sample_reductions` |
| `ModelUsage` | `input_tokens` (excludes cached), `output_tokens`, `total_tokens`, `input_tokens_cache_write`, `input_tokens_cache_read`, `reasoning_tokens`, `total_cost: float \| None` ("Total cost in dollars for this usage"); `__add__` sums all including cost |
| `ModelOutput` | `model`, `choices`, `completion`, `usage`, `fallback: ModelFallback{model, fallback_model}`, `time`, `metadata`, `error` |

### Model providers and pinning

Model ids are `provider/model` strings (`openai/gpt-4o-mini`, `anthropic/claude-sonnet-4-0`, `google/gemini-2.5-pro`, `together/meta-llama/...`); providers: OpenAI, Anthropic, Google, Grok, Mistral, DeepSeek, Moonshot, Perplexity, Bedrock, SageMaker, Azure, Groq, Together, Fireworks, Cloudflare, HF Inference, SambaNova, plus local HF/vLLM/Ollama/llama-cpp/SGLang. `-M key=value` passes provider args; `model_roles` bind names such as `grader`.

Pinning is by the string you pass; Inspect adds a bundled model database (`prior/inspect_ai/src/inspect_ai/model/_model_data/{openai,anthropic,gdm,deepseek,grok,mistral,moonshotai,zai,together,fireworks}.yml`) with `display_name`, `release_date`, `knowledge_cutoff_date`, `context_length`, `output_tokens`, `reasoning`, `family`, `snapshot` and `versions:` sub-entries (e.g. `gpt-4o` -> `gpt-4o-2024-11-20: snapshot "2024-11-20"`), exposed as `ModelInfo` via `get_model_info()`. Zero of these YAML files carry `cost:` entries, so prices are never bundled.

Does the log record the API-returned model version? Partly, and it differs by provider (read from `_providers/` at HEAD):

| Provider | `ModelOutput.model` | Source line |
|---|---|---|
| OpenAI Chat Completions | `completion.model` (API response) | `model/_openai.py` `model_output_from_openai` |
| OpenAI Responses | `response.model` unless overridden | `model/_openai_responses.py` line 672 |
| Anthropic | `message.model`, or the fallback target if a server-side fallback block is present | `_providers/anthropic.py` lines 3515-3520, 3648 |
| Google | `response.model_version or service_model_name()` | `_providers/google.py` line 580 |
| Generic openai_compatible (DeepSeek, Together, etc.) | `service_model_name()` = the requested `model_name` | `_providers/openai_compatible.py` line 422 (agent-eval's DeepSeek note says the logged name was the provider's response name, so some compatible providers differ; NOT VERIFIED per provider) |

The usage dictionaries (`EvalSample.model_usage`, `EvalStats.model_usage`) are keyed by `f"{model}"`, i.e. the requested `provider/model` string, not the response id (`_model.py` `record_and_check_model_usage` line 2957). `EvalSpec.model` is the requested string. So: the response id is available per `ModelEvent`, the aggregate keys are the requested id, and neither is guaranteed to be a dated snapshot unless you pass one.

### Cost fields

Inspect now has native cost support (present by 0.3.180, 20 Feb 2026, when a `cost_limit()` context manager appears in the CHANGELOG; the exact release that introduced `ModelCost` is NOT VERIFIED because the CHANGELOG has no line naming it). Mechanism (`prior/inspect_ai/src/inspect_ai/model/_model_data/model_data.py` lines 10-31, `_model_info.py` lines 446-460, `_model.py` lines 3099-3134, `_eval/eval.py` lines 789-795):

- `ModelCost(input, output, input_cache_write, input_cache_read)` in dollars per million tokens; `input_cache_write` must be the default-TTL rate (Anthropic 1-hour writes are multiplied by 2/1.25 at compute time when `-M cache_ttl=1h`).
- `set_model_cost("openai/gpt-4o", ModelCost(...))` raises `ValueError` if the model is not in the bundled database or the custom registry; register unknown models first with `set_model_info(model, ModelInfo(...))` (0.3.242 note: lookups happen under both the user-facing string and the canonical name so routed providers such as `together` keep their cost).
- `--model-cost-config pricing.yaml` (also `eval(model_cost_config=...)`, `eval_set(...)`, env `INSPECT_EVAL_MODEL_COST_CONFIG`) with a YAML/JSON map `provider/model: {input, output, input_cache_write, input_cache_read}`.
- `compute_model_cost(cost_data, usage, cache_ttl)` = input x input/1e6 + output x output/1e6 + cache_write x rate/1e6 + cache_read x rate/1e6; result written to `ModelUsage.total_cost` on every `ModelEvent`, summed into the per-model usage dicts and `sample_total_cost()`, checked against `cost_limit`.
- `cost_limit` (Task, eval(), CLI) "requires model cost data ... An error will be raised if a cost limit is set without cost data for all models used in the evaluation".
- Whether `inspect view` displays `total_cost`: NOT VERIFIED (docs mention token usage only).

### Sandboxes

`sandbox="docker"` or `("docker", "compose.yaml")` or `SandboxEnvironmentSpec("docker", ComposeConfig(...))`, per task or per sample. Compose keys used by the docs: `image`, `build`, `x-local: true`, `init: true`, `command: tail -f /dev/null`, `cpus`, `mem_limit`, `network_mode: none`; multiple services addressed by `sandbox("name")`. Network: `network_mode: none` blocks the container; omitting it gives bridge with internet; `internal: true` networks give service-to-service only; the docs warn the setting "applies only to processes inside the container. It does not restrict network access from the evaluation process or model provider". API: `sandbox().exec(cmd, input, cwd, env, user, timeout, timeout_retry, concurrency)` (10 MB output cap, `INSPECT_SANDBOX_MAX_EXEC_OUTPUT_SIZE`), `read_file` (100 MB cap), `write_file`, `connection()`, `exec_remote()`. Providers: `docker`, `local`, `k8s`, `daytona`, `modal`, `ec2`, `proxmox`, `vagrant`. Concurrency: `max_sandboxes`, `max_subprocesses`, `max_samples`, `INSPECT_DOCKER_CLI_CONCURRENCY` (asta-bench README recommends `max_samples` <= cores, CLI concurrency >= 2N). Docker Engine >= 24.0.6, Compose >= 2.21.

### eval-set and viewer

`inspect eval-set --log-dir D tasks...`: retries failed tasks (`--retry-attempts` default 10, `--retry-immediate`/`--retry-wait` 30 s exponential, `--retry-connections` 1.0, `--no-retry-cleanup`), reuses completed samples across retries keyed by explicit `Sample.id` (auto ids break under shuffle), is idempotent on re-invocation, and can publish a static viewer with `--bundle-dir`/`--bundle-overwrite`; `eval_set()` returns `(success: bool, logs)`. `inspect view --log-dir --port --host --trusted-origin --unsafe-allow-unauthenticated` shows transcripts, scores, metadata, git revision and "model token usage"; `inspect view bundle --log-dir logs --output-dir logs-www` (supports `hf/` prefix for HF Spaces).

### Design constraints implied for FrugalMind (from Inspect)

1. Use Inspect's native `ModelCost` path for the live per-sample `total_cost` and `cost_limit`, but still recompute cost offline from token counts with FrugalMind's own dated map; the two must agree to the cent, and the offline one is what gets published (Inspect's number depends on whatever map was loaded at run time).
2. Register every model you intend to run with `set_model_info` plus `set_model_cost` before `eval()`, and fail the run if any model lacks a price; `cost_limit` already enforces this.
3. Record three ids per run: the requested `provider/model` string (`EvalSpec.model`, usage-dict keys), the response-side id from each `ModelEvent.output.model` (differs by provider, see table), and the snapshot date from `get_model_info().snapshot`; refuse "unpinned" ids on the test split.
4. Use `Epochs(k, ["mean", "collect"])` for repeats so the log carries both the reduced score and the raw per-epoch values; compute between-epoch SD from `EvalLog.reductions` or `scores="unreduced"` metrics. Keep k >= 3 and report `stderr` across samples separately from SD across epochs.
5. Give every `Sample` an explicit stable `id`; eval-set's retry/resume and reduction bookkeeping depend on it.
6. For the OOI/EarthScope coding tasks, do not rely on `network_mode: none`; allow egress but pin it with an `internal: true` network plus an explicit proxy/allow-list container, since the model-provider calls come from the host process anyway. Log every outbound host from the proxy so the harness can prove which endpoints were touched and when.
7. Put the corpus snapshot id and date cutoff into `Task.metadata` and each `Sample.metadata` (they land in `EvalSpec.metadata` and `EvalSample.metadata`), and stamp `Task.version` whenever the corpus or rubric changes; `EvalSpec.task_version`, `revision.commit`, `revision.dirty` and `packages` are then sufficient provenance.
8. Store logs as `.eval`, read headers with `header_only=True` for aggregation, stream samples with `read_eval_log_samples()`; asta-bench reports 30-minute scoring passes over multi-GB directories.
9. Keep FrugalMind's scorer environment pinned to one Inspect version and record it in `packages`; the Inspect API surface (limits, cost, reducers) has moved every release in 2026.

### What FrugalMind could adopt directly vs must build (Inspect)

Adopt directly: Task/Sample/Solver/Scorer/Metric/Reducer framework; `.eval` logging with `EvalSpec.revision` and `packages`; docker sandboxes with compose; `Epochs` with `collect`; `stderr(cluster=)` and `bootstrap_stderr`; `cost_limit` and `--model-cost-config`; `eval-set` retry and bundle; `bridge()` for third-party agent frameworks; `inspect view bundle` for shareable logs.

Must build: the dated price map and its offline recomputation; the response-model-id extraction and pinning check; between-epoch variance and Pareto-with-CI plots (Inspect reduces epochs but does not plot score against cost); the egress-logging proxy; corpus-snapshot management for the drifting paper index and the sensor-metadata index; leaderboard bundling (agent-eval covers the HF part if wanted).

## 4. Cross-cutting summary

| FrugalMind requirement | AstaBench/agent-eval | Inspect | Gap for FrugalMind |
|---|---|---|---|
| Frozen price map | litellm map pinned by commit, undated, keyed by log model string, hash printed, URL stored | `ModelCost` per model, $/M tokens, loaded at run time, no bundled prices | Dated map, offline recompute, response-id keying |
| Accuracy jointly with cost | per-sample cost lists, task mean cost, Pareto sweep | `total_cost` per event/sample | Aggregate-level CI on cost |
| Repeated runs | none (one log per task) | `Epochs(k, reducers)`, `collect` | Between-run SD, Pareto with repeat CI |
| Pinned model versions | "(unpinned)" flag in display names only | snapshot metadata in model database; response id per event for 3 providers | Hard refusal of unpinned ids on test |
| Date-restricted corpus | per-task constant, client-side tool wrapping, scorer re-check | none | Snapshot ids for drifting indices; egress policy for live APIs |
| Pareto plots | matplotlib and plotly frontier sweeps, task-level 1.96 x stderr bars | none | Aggregate CI, per-repeat points |