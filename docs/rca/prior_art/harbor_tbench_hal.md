# Prior art for Repère: Harbor, Terminal-Bench 2.0 artifact pattern, HAL

Date of survey: 2026-09-14. Everything below was read from cloned repositories, the arXiv PDF (text extracted with `pdftotext`), the GitHub API, the HuggingFace API, and the tbench.ai and hal.cs.princeton.edu sites. Nothing was rerun. Items I could not confirm are marked NOT VERIFIED.

Clones live under `<scratch>/prior/` (abbreviated `prior/` below): `harbor/`, `hal-harness/`, `terminal-bench/` (legacy 1.0 harness), `tb-leaderboard/` (= `harbor-framework/terminal-bench`, current), `meta-harness-tbench2-artifact/`, plus `hal_2510.11977.pdf` and `hal_2510.11977.txt`.

## Verdict in three lines

1. Harbor is the live, maintained substrate (commit today, release every 2 to 4 weeks, Apache-2.0, Zenodo DOI). Its task format, sandbox network policy, ATIF trajectories, `lock.json`, and `n_attempts`/pass@k are directly usable. It has no price table: `cost_usd` comes from LiteLLM's runtime pricing or from the agent's own self-report.
2. Terminal-Bench's artifact pattern is: agent code in its own tagged repo; run records (config + per-trial result + trajectories) in a separate immutable store (HF dataset for 2.0, Harbor Hub for 4.0); a submission JSON naming agent version, model id, reasoning effort, trial ids, accuracy ± 95% CI, token splits and dollars; CI that rejects timeout or resource overrides, requires 5 trials per task, and runs an LLM judge for reward hacking. There is no DOI for individual submissions; DOIs exist only for the harness and the dataset repo.
3. HAL's harness is archived (July 2026) and its Inspect integration was deleted in January 2026, but its paper is the best written record of what breaks: single runs without confidence intervals, provider weight swaps behind stable endpoints, quantization drift through aggregators, silent rate-limit failures, price changes of 80%. Its checked-in price dictionary with cache-tier overrides and a fail-fast "unknown model" check is the one piece of HAL code worth copying.

Identifier corrections for the user's notes:

| Note said | Reality |
|---|---|
| `github.com/laude-institute/harbor` | Redirects to `github.com/harbor-framework/harbor` (CITATION.cff and GitHub API agree). Same project. |
| `github.com/laude-institute/terminal-bench` is Terminal-Bench 2.0 | That repo is the legacy 1.0 harness (`tb` CLI, v0.2.18, last push 2026-07-11); its README says use Harbor. TB 2.0 tasks live in `laude-institute/terminal-bench-2` (redirects to `harbor-framework/terminal-bench-2`, 89 tasks, Apache-2.0, last push 2026-04-30). The current benchmark repo is `harbor-framework/terminal-bench` (created 2026-01-25, tags v3.0.0 and v4.0.0). tbench.ai today shows Terminal-Bench 4.0 (released 2026-08-28). |
| `stanford-iris-lab/meta-harness-tbench2-artifact` | Exists. Created 2026-03-26, one commit, 1210 stars, no LICENSE file. The paper's framework code is a different repo, `stanford-iris-lab/meta-harness` (MIT, created 2026-04-15), paper arXiv:2603.28052 "Meta-Harness: End-to-End Optimization of Model Harnesses", Lee, Nair, Zhang, Lee, Khattab, Finn. |
| arXiv:2510.11977 is the HAL paper | Confirmed: "Holistic Agent Leaderboard: The Missing Infrastructure for AI Agent Evaluation", Kapoor and Stroebl (equal), ..., Narayanan, v1 submitted 13 Oct 2025, 15 pages. The hal-harness README's BibTeX uses a different title ("HAL: A Holistic Agent Leaderboard for Centralized and Reproducible Agent Evaluation", 3 authors, ICLR 2026); the site says the paper was accepted to ICLR 2026. Same project, two titles. |

---

## 1. Harbor (harbor-framework/harbor)

### Metadata

| Item | Value | Source |
|---|---|---|
| Version | 0.23.0 | `prior/harbor/pyproject.toml` |
| Latest release | v0.23.0, 2026-09-12; earlier v0.22.0 (08-22), v0.21.0 (08-10), v0.20.0 (07-18), v0.18.0 (07-07) | GitHub releases API |
| HEAD | `0d67ca4b`, 2026-09-14 10:47 PDT, "Add --use-static-ip flag for hosted launches (#3213)" | `git log` |
| Repo created | 2025-08-04; 5,228 stars; not archived | GitHub API |
| License | Apache-2.0 (`LICENSE`, `pyproject.toml`) | |
| Python | `requires-python >= 3.12`; `.python-version` = 3.13 | |
| Install | `uv tool install harbor` or `pip install harbor`; sandbox extras `harbor[daytona]`, `[e2b]`, `[modal]`, `[runloop]`, `[islo]`, `[langsmith]`, `[cua]`, `[cloud]` for all; build backend `uv_build`; workspace packages `packages/rewardkit`, `packages/harbor-langsmith`, `packages/harbor-atif2otel` | `pyproject.toml`, `docs-mintlify/core-concepts/sandboxes/pre-integrated-sandboxes.mdx` |
| Release policy | stable "usually biweekly", nightly `<next-patch>.dev<timestamp>` to PyPI; minor bump = breaking change | `docs-mintlify/contributing/release-policy.mdx` |
| DOI | concept 10.5281/zenodo.20953922; v0.23.0 record 10.5281/zenodo.22719635 (2026-09-12), linked to `tree/v0.23.0` | README, `CITATION.cff`, Zenodo API |
| Telemetry | on by default (PostHog; job-level token usage, cost, reward); `HARBOR_TELEMETRY=off` | `docs-mintlify/telemetry/telemetry.mdx` |
| Dependencies of note | `litellm>=1.92.0`, `pydantic>=2.12`, `supabase>=2.28`, `fastapi`, `dirhash` | `pyproject.toml` |

Maintenance is intense: `CHANGELOG.md` is 50 KB and carries "Breaking" entries in the unreleased section (prompt templates now Jinja-sandboxed; built-in agents must declare `options_model`; judge TOMLs validated by Pydantic). A Repère paper artifact must pin the exact Harbor version (the 4.0 leaderboard tooling itself only pins `harbor[modal]>=0.20.0`).

### Task format

Files: `prior/harbor/docs-mintlify/core-concepts/tasks/{overview,configuration,instruction,solution,verifier,environment,network-policies,resources}.mdx`; schema in `prior/harbor/src/harbor/models/task/config.py` (`TaskConfig`, `schema_version` default "1.4" in code, "1.3" in docs).

```
instruction.md          # markdown handed to the agent; leading <!-- --> comment stripped (canary string slot)
task.toml               # config + metadata
environment/Dockerfile  # or docker-compose.yaml, or [environment].docker_image with no dir
solution/solve.sh       # optional; used only by the built-in `oracle` agent
tests/test.sh           # verifier entrypoint; must write /logs/verifier/reward.txt (scalar) or reward.json (labeled dims)
```

`task.toml` sections (all optional; defaults in `config.py`):

| Section | Key fields | Default |
|---|---|---|
| `[task]` | `name` (org/name), `version`, `authors`, `keywords` | none |
| `[metadata]` | free-form | |
| `[environment]` | `network_mode` ∈ {public, no-network, allowlist}; `allowed_hosts`; `docker_image`; `os`; `cpus`, `memory_mb`, `storage_mb`, `gpus`, `gpu_types`, `tpu`; `env` with `${VAR}` templating; `[[environment.mcp_servers]]`; `skills_dir`; `healthcheck`; `workdir`; `build_timeout_sec` | `network_mode = "public"`, build 600 s |
| `[agent]` | `timeout_sec`, `user`, phase override `network_mode`/`allowed_hosts` | no timeout |
| `[verifier]` | `timeout_sec`, `env`, `user`, `environment_mode` ∈ {shared, separate}, `[verifier.environment]` (own image built from `tests/`), `[[verifier.collect]]` hooks, phase `network_mode` | 600 s, shared |
| `[solution]` | `env` | |
| root | `artifacts = [...]` (paths snapshotted after the agent phase; copied into a separate verifier sandbox), `source`, `multi_step_reward_strategy`, `[[steps]]` for multi-step tasks | |

The deprecated `allow_internet` boolean maps to `public`/`no-network`. Multi-step tasks put per-step `instruction.md`, `tests/`, `solution/` under `steps/<name>/`. Tasks are explicitly designed to have no dependency on the Harbor package ("Harbor tasks have no dependency on the Harbor framework", overview.mdx).

Verifier interface: the default `Verifier` uploads `tests/` to `/tests/`, runs `test.sh` in the task workdir, downloads `/logs/verifier/`, parses the reward file (`reward.json` preferred when both exist; missing reward → `RewardFileNotFoundError`, non-retryable). A host-side alternative implements `BaseVerifier.verify() -> VerifierResult(rewards={...})`, selected by `verifier.import_path` (`docs-mintlify/core-concepts/jobs/custom-verifiers.mdx`, `src/harbor/verifier/`). LLM- or agent-as-judge is packaged as `harbor-rewardkit` (`packages/rewardkit`, judge `.toml` with `[[criterion]]`, weights, aggregation; now schema-validated at discovery).

### Agent interface

`prior/harbor/src/harbor/agents/base.py` (`BaseAgent`) and `src/harbor/agents/installed/base.py` (`BaseInstalledAgent`); docs `docs-mintlify/core-concepts/agents/custom-agents.mdx`.

```python
class BaseAgent(ABC):
    @staticmethod
    def name() -> str: ...
    def version(self) -> str | None: ...           # recorded in result.json agent_info.version
    async def setup(self, environment: BaseEnvironment) -> None: ...
    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None: ...
    def populate_context_post_run(self, context: AgentContext) -> None: ...
    capabilities: AgentCapabilities   # atif=True only if the agent writes logs_dir/trajectory.json
    options_model: type[AgentOptions] | None   # kwargs schema, validated at preflight
```

Installed agents (Claude Code, Codex, Gemini CLI, OpenHands, aider, mini-swe-agent, ... 50 files under `src/harbor/agents/installed/`) run inside the container; external agents (Terminus-2, `src/harbor/agents/terminus_2/`) run the loop on the host and act through `environment.exec/upload/download`. A custom agent is passed as `-a module.path:ClassName` (older CLI: `--agent-import-path`, which the Meta-Harness README still uses). Model is `-m provider/model`; extra constructor args `--ak key=value`; agent-phase env `--ae KEY=VAL`. Credentials are scoped: `environment.env` reaches the whole sandbox, `agents[].env` only the agent phase, `verifier.env` only the verifier phase (`docs-mintlify/core-concepts/jobs/environment-variables.mdx`).

`AgentContext` (`src/harbor/models/agent/context.py`): `n_input_tokens` (includes cache), `n_cache_tokens`, `n_output_tokens`, `cost_usd`, `model_usage: dict[model -> ModelUsage]` (backfilled from the ATIF trajectory), `rollout_details`, `metadata`.

### Sandbox and execution backends

`BaseEnvironment` (`src/harbor/environments/base.py`): `start`, `stop`, `exec(command, cwd, env, timeout_sec, user)`, `upload_file/dir`, `download_file/dir`, `capabilities: EnvironmentCapabilities`, optional `preflight()`. Selected with `-e <type>` or `-e module:Class`.

| Class | Backends (files in `src/harbor/environments/`) |
|---|---|
| Local | `docker` (default), `podman`, `apple-container`, `singularity` |
| Remote | ack, beam, blaxel, cua-cloud, cwsandbox, daytona, e2b, ec2, gke, hf-sandbox, hyperbrowser, islo, langsmith, modal, novita, opensandbox, openshift, runloop, runta, skypilot, tensorlake, use-computer, vercel, wandb |

Capability tables (GPU, compose, network allowlist, CPU/memory limit vs request) are in `pre-integrated-sandboxes.mdx`. Resource enforcement policy per run: `--cpus/--memory auto|limit|request|guarantee|ignore`. Concurrency `-n`; attempts `-k` (`n_attempts`); retries `-r` with `retry.exclude_exceptions` defaulting to `AgentTimeoutError, VerifierTimeoutError, RewardFileNotFoundError, RewardFileEmptyError, VerifierOutputParseError, ApiUsageLimitError, AgentSafetyRefusalError, AgentAuthenticationError, ModelNotFoundError` (`src/harbor/models/job/config.py`).

### Network control inside tasks

`docs-mintlify/core-concepts/tasks/network-policies.mdx`; enforcement code `src/harbor/environments/docker/harbor-docker-egress-control-sidecar/` (a `gost` proxy image pinned by digest plus an nftables ruleset `gost_egress`; `entrypoint.sh` applies `allow-all`, `deny-all`, or `allow <hosts>`; `docker-compose-egress-control.yaml`, `docker-compose-no-network.yaml`).

| Fact | Consequence |
|---|---|
| Default `network_mode` is `public` | You must opt in to restriction per task. |
| `allowed_hosts` accepts exact hostnames, `*.suffix` wildcards, IPv4/IPv6 literals, CIDRs; never URLs or ports (`_validate_allowed_host_names`) | OOI M2M and FDSN endpoints must be expressed as hostnames, e.g. `ooinet.oceanobservatories.org`, `service.iris.edu` (or their EarthScope successors). |
| Phase overrides: `[agent]` applies to `agent.run()` only (not `setup()`), `[verifier]` to `verify()` | Install the agent under the public baseline, then narrow to data hosts + LLM API during the run, and `no-network` for the verifier. |
| Dynamic per-phase switching requires provider support (docker/podman with nftables, daytona, e2b, modal, novita, islo, beam, hyperbrowser, vercel, tensorlake); a task requesting an unsupported mode is rejected at validation rather than run weaker | Pick a backend from that list; GKE and EC2 cannot do allowlists. |
| Run-level additions: `--allow-agent-host`, `agents[].extra_allowed_hosts`, `environment.extra_allowed_hosts` | Leaderboard CI should forbid these the same way it forbids timeout overrides. |

### Trajectories, logs, results, cost

| Artifact | Where | Notes |
|---|---|---|
| ATIF trajectory (Agent Trajectory Interchange Format) | `<trial>/agent/trajectory.json`; spec `prior/harbor/rfcs/0001-trajectory-format.md`; models `src/harbor/models/trajectories/`; validator `python -m harbor.utils.trajectory_validator` | v1.7 in docs, v1.8 in changelog (audio). Per-step `metrics` (tokens, `cost_usd`), `final_metrics`, `agent.model_name`, subagent trajectories. Judges (TB leaderboard) require it for every passing trial. |
| Trial result | `<trial>/result.json` → `TrialResult` (`src/harbor/models/trial/result.py`) | `task_checksum` (sha256), `task_id` (git url + commit + path), `agent_info{name, version, model_info{name, provider}}`, `agent_result` (AgentContext), `verifier_result.rewards`, `exception_info`, timing for environment_setup / agent_setup / agent_execution / verifier. `compute_token_cost_totals()` sums input/cache/output/cost. |
| Trial lock | `<trial>/lock.json` → `TrialLock` (`src/harbor/models/job/lock.py`) | task digest `sha256:`, agent config, environment config, verifier config incl. resolved mode, skills digests, extra-instruction digests, regrade source. Uploads to the Hub require it (`src/harbor/upload/uploader.py::_read_trial_lock_for_upload`). |
| Job lock | `<job>/lock.json` → `JobLock` | `harbor{version, git_commit_hash, is_editable}`, `n_concurrent_trials`, `retry`, all `TrialLock`s. This is the only place the harness version is recorded. |
| Job result | `<job>/result.json` → `JobStats` (`src/harbor/models/job/result.py`) | totals `n_input_tokens`, `n_cache_tokens`, `n_output_tokens`, `cost_usd`; per `agent__model__dataset` key: `metrics`, `pass_at_k`, `reward_stats`, `exception_stats`. |
| Verifier logs | `<trial>/verifier/` (`reward.txt|json`, `test-stdout.txt`, `ctrf.json` when pytest-json-ctrf used) | |
| Artifacts | `<trial>/artifacts/...` + `manifest.json` (status ok/empty/failed/skipped) | Also the transfer channel into a separate verifier sandbox; enables `harbor job regrade` with no new agent cost. |
| Viewer | `harbor view jobs` (tabs Agent, Verifier, Artifacts, Config, Lock) | |
| Upload | `harbor run --upload` / `harbor upload jobs/<name>` → Harbor Hub (Supabase; `src/harbor/upload/`, `src/harbor/hub/`) | Private by default. Hub leaderboards: `harbor hub leaderboard init|create|update|row ...`, rows carry `trial_ids` for provenance (`docs-mintlify/core-concepts/harbor-hub/leaderboards.mdx`, `docs/content/docs/hosted-harbor/cli-leaderboards.mdx`). |
| Trajectory analysis | `harbor analyze <job-dir> -m <model> -r <rubric.toml>` (`src/harbor/analyze/`) | LLM rubric over trials: reward hacking, task-spec issues, per-trial summaries. |

How `cost_usd` is produced (the load-bearing finding):

- Harbor's own LLM layer (`src/harbor/llms/lite_llm.py::_extract_cost`) takes `response._hidden_params["response_cost"]` if LiteLLM set it, else `litellm.completion_cost(completion_response=response)`, else 0.0. That is LiteLLM's bundled `model_prices_and_context_window.json` at whatever LiteLLM version is installed. There is no price table in the Harbor tree (grep for `model_prices|pricing` in `src/harbor` returns nothing except `llms/utils.py`, which requires `input_cost_per_token`/`output_cost_per_token` in `model_info` for `hosted_vllm` models).
- Installed agents self-report. `src/harbor/agents/installed/claude_code.py::_parse_total_cost_from_stream_json` reads `total_cost_usd` from Claude Code's `{"type":"result",...}` line; if absent, `_estimate_step_costs` prices each step with `litellm.cost_per_token(...)` and tags `metrics.extra["cost_source"] = "litellm_estimate"`.
- The 4.0 leaderboard sums these per-trial values into `total_cost_usd`; the Harbor-Index blog states costs are "reconstructed from token usage, priced at each provider's public API rates" with OpenRouter rates for open models. No pricing date is stored anywhere in the results.

### Datasets and registries

`registry.json` (`docs-mintlify/core-concepts/datasets/registries.mdx`) is a JSON array of `{name, version, description, tasks[{name, git_url, git_commit_id, path}], metrics}`. The 13.6 MB `prior/harbor/registry.json` has 80 datasets; entry `terminal-bench@2.0` has 89 tasks pinned to `https://github.com/laude-institute/terminal-bench-2.git` commit `69671fbaac6d67a7ef0dfec016cc38a64ef7a77c`. The default registry is now Harbor Hub (`org/name@ref`, refs resolve to `sha256:` content digests; `DatasetConfig._get_package_task_configs` rewrites `ref` to the digest "for config version tracking"). Metrics: default mean with missing rewards counted as 0; custom `metric.py` (`uv-script`) reads a rewards JSONL and writes a JSON object.

### Design constraints implied for Repère (Harbor)

1. Task directory must be `instruction.md` + `task.toml` + `environment/Dockerfile` (or pinned `docker_image` digest) + `tests/test.sh` writing `/logs/verifier/reward.json` with labeled dimensions (e.g. `correctness`, `data_integrity`, `citation_accuracy`), and must import nothing from the harness, so tasks outlive harness releases.
2. Every task must declare `[environment] network_mode = "allowlist"` with an explicit `allowed_hosts` list (data hosts, package index, the agent's LLM API host), `[verifier] network_mode = "no-network"`, and `[verifier] environment_mode = "separate"` with a `tests/Dockerfile`; run only on backends that advertise `dynamic_network_policy`, and have CI reject tasks that fall back to `public`.
3. Record per trial: task `sha256` digest, dataset git commit, agent `version()`, `model_info{name, provider}`, and the harness version + commit from `JobLock`; a paper artifact is incomplete without the job `lock.json`.
4. Cost must not be taken from `cost_usd` as delivered. Recompute from ATIF per-step token counts (uncached input, cached input, cache write, output) against a Repère-owned price table keyed by `(provider/model-id, effective_date)`, store both `cost_usd_reported` and `cost_usd_table` with `cost_source` and the price-table digest.
5. Require dated model snapshot ids in `-m` (reject aliases such as `claude-opus-4-6` without a date or a provider-side version) and record `reasoning_effort` as a first-class field; Harbor stores only the string the user typed.
6. Use `n_attempts >= 5` (`-k 5`) as the default for any reported number; report mean ± 95% CI and pass@k from `JobStats`, plus the cost distribution across attempts, not just the mean.
7. Keep `retry.exclude_exceptions` at Harbor's default (timeouts and missing reward are never retried) and count errored trials as reward 0, but add a Repère exception taxonomy that separates upstream data-service failures (HTTP 5xx from the observatory API, FDSN timeouts) from agent failures, recorded in `exception_info` and reported as a separate column.
8. Declare `artifacts` (fetched data files, generated code, RAG answer JSON) in `task.toml` so verifier fixes can be applied with `harbor job regrade` at zero LLM cost; treat verifier changes as "minor" versions per the Terminal-Bench semantic-versioning rule.
9. Fix `timeout_sec`, `cpus`, `memory_mb` per task after a calibration run with headroom, and forbid `timeout_multiplier != 1`, `override_*`, and `extra_allowed_hosts` in any reported run.
10. Emit ATIF (`capabilities.atif = True`) from the RAG agents too, since RAG agents are not terminal agents: wrap them as external `BaseAgent`s that call the LLM from the host, write the answer and retrieved-evidence list into the container, and let `tests/test.sh` grade it.

### What Repère could adopt directly vs must build (Harbor)

| Adopt as is | Must build |
|---|---|
| Task format, `task.toml` schema and Pydantic validation | Checked-in, dated price table and cost recomputation from ATIF |
| Docker sandbox with egress-control sidecar and per-phase policies | Model-snapshot policy (reject undated ids; record provider endpoint, region, quantization if via aggregator) |
| ATIF trajectory format, validator, viewer | Record/replay (cassette) of observatory and FDSN HTTP traffic as a task artifact, plus pinned data windows, because live services drift (Terminal-Bench 2.1 found 9 of 89 tasks broken by external dependency drift) |
| `n_attempts`, pass@k, `JobStats`, retry policy | Failure taxonomy separating data-service outages from agent errors |
| `lock.json` (trial + job) | DOI packager: bundle job dir + lock + price table + agent repo snapshot for Zenodo |
| `registry.json` with commit-pinned tasks, or Harbor Hub datasets with digests | RAG-specific verifiers (citation precision/recall against a frozen corpus index) via RewardKit criteria or plain pytest in `tests/` |
| `harbor job regrade`, separate verifier | External-agent wrappers for the literature-RAG and metadata-RAG agents |
| `harbor analyze` rubric runner, RewardKit judges | Pinning discipline: `uv.lock` per paper artifact with the exact Harbor version, because minor releases are breaking |

Risk to state plainly: Harbor is a moving target (v0.18 → v0.23 in ten weeks with breaking changes), it phones home by default, and its Hub is a hosted Supabase service. A paper artifact should not depend on the Hub being reachable.

---

## 2. Terminal-Bench 2.0 and the Meta-Harness artifact pattern

### What "Terminal-Bench 2.0" is, and where the artifact went

| Version | Date | Task set | Harness | Submission store |
|---|---|---|---|---|
| 1.0 | 2025-05-19 | `terminal-bench-core` 0.1.1 (branch `dataset/terminal-bench-core/v0.1.x`) | `laude-institute/terminal-bench` (`tb run`) | Supabase via `tb` CLI (`prior/terminal-bench/CLAUDE.md`) |
| 2.0 | 2025-11-07 ("Terminal-Bench 2.0 and Harbor") | 89 tasks, `laude-institute/terminal-bench-2` @ `69671fb` | Harbor (`harbor run -d terminal-bench@2.0`) | HF dataset `alexgshaw/terminal-bench-2-leaderboard` (now `harborframework/terminal-bench-2-leaderboard`), PR-based |
| 2.1 | 2026-05-06 | 28 of 89 tasks fixed (external dependency drift 9, resource mismatch 8, misspecification) | Harbor | same, closed 2026-05-14 |
| 3.0 | 2026-07-30 | 74 tasks, 7 domains; "continuous benchmark"; separate verifier container mandatory | Harbor | Harbor Hub + `leaderboard/` package in `harbor-framework/terminal-bench` |
| 4.0 | 2026-08-28 (tag v4.0.0 2026-08-26) | 8 tasks removed (saturated 2, refusals 2, public solutions 2, quality 2), 19 fixed, flat 8 h agent timeout | Harbor | same; community submissions currently closed |

Sources: `prior/harbor/README.md`, `prior/harbor/docs/content/docs/tutorials/running-terminal-bench.mdx` (names the HF repo and says "open a PR there"), tbench.ai news posts (`/news/announcement-2-0`, `/news/terminal-bench-2-1`, `/news/leaderboard-integrity-update`, `/news/continuous-benchmarks`, `/news/terminal-bench-3-0`, `/news/terminal-bench-4-0`), `prior/tb-leaderboard/README.md`, `CITATION.cff` (v4.0.0, 2026-08-26, DOI 10.5281/zenodo.22105680; Zenodo API resolves concept 10.5281/zenodo.22105680, version DOI 10.5281/zenodo.22105681).

### The Meta-Harness artifact, concretely

Artifact repo `prior/meta-harness-tbench2-artifact/` (commit `57fefdb2`, 2026-03-26 11:26 PDT, "Meta-Harness agent for Terminal-Bench 2.0 (76.4%)"):

| File | Content |
|---|---|
| `README.md` | Result table 76.4% (89 tasks × 5 trials, Claude Opus 4.6; Easy 100.0 n=4, Medium 81.1 n=55, Hard 64.7 n=30) and the exact command: `harbor run --agent-import-path agent:AgentHarness -d terminal-bench@2.0 -m anthropic/claude-opus-4-6 -e runloop -n 20 --n-attempts 5` |
| `agent.py` (52.9 KB) | `class AgentHarness(Terminus2)` importing `harbor.agents.terminus_2`, `harbor.llms.chat`, `harbor.models.trajectories` |
| `anthropic_caching.py` | adds `cache_control: ephemeral` to the last 3 messages |
| `prompt-templates/terminus-kira.txt` | prompt |
| `pyproject.toml` | `harbor>=0.1.44`, `litellm<1.82.7`, `anthropic`, `tenacity`; `requires-python >= 3.12` |
| (absent) | LICENSE, CITATION.cff, uv.lock, trajectories, results |

Leaderboard record (HF dataset `harborframework/terminal-bench-2-leaderboard`, 76 entries under `submissions/terminal-bench/2.0/`, read via the HF tree API):

```
submissions/terminal-bench/2.0/Meta-Harness__Claude-Opus-4.6/
  metadata.yaml                          # agent_url -> the artifact repo; display names; models[{model_name, model_provider, ...}]
  2026-03-26__meta-harness-v1/
    config.json                          # Harbor JobConfig: n_attempts 5, runloop, agent import_path, dataset terminal-bench@2.0 via registry URL
    result.json                          # JobStats: n_total_trials 445, n_errors 35, mean 0.7640449438202247
    adaptive-rejection-sampler__9MBtkGv/ # one dir per trial (445 = 89 x 5)
      config.json                        # task git_url + commit 69671fb..., model anthropic/claude-opus-4-6, timeout_multiplier 1.0
      result.json                        # task_checksum sha256, agent_info{name terminus-kira-env-bootstrap, version 1.1.0}, agent_result{tokens, cost_usd 3.29}, verifier_result, exception_info, timings
      exception.txt
      agent/episode-0 ... episode-19/    # native Terminus-2 logs
      verifier/ctrf.json, reward.txt, test-stdout.txt
```

Two observations from those files:

- The job config's agent import path is `agents_proposed.evo_env_bootstrap:AgentHarness` and the recorded agent name is `terminus-kira-env-bootstrap` v1.1.0; the artifact repo exposes `agent:AgentHarness`. The published code is a cleaned copy, not byte-identical to what produced the run; nothing links the two by digest.
- No Harbor version appears in `config.json` or `result.json` (no `lock.json` existed at that time). Which Harbor version produced the 76.4% is NOT VERIFIED; the pyproject floor is `>=0.1.44`.

Whether the Meta-Harness row is still displayed on tbench.ai is NOT VERIFIED (the site now shows only 4.0; a 2.1 leaderboard link exists in the 2.1 post but I did not retrieve it). The Harbor Hub page for the TB dataset returned a task list without the leaderboard tab content.

### Separation of frozen submission from maintained harness

For 2.0 (HF README, `harborframework/terminal-bench-2-leaderboard`):

- Submission = `metadata.yaml` + full job directory. Validation bot on PR: `timeout_multiplier == 1.0`; no `override_timeout_sec`, `max_timeout_sec`, verifier timeout overrides, `override_cpus/memory_mb/storage_mb`; every trial has a valid `result.json`; trial dirs contain the other run artifacts; ≥ 5 trials per task (`-k 5`); "Agents cannot access the Terminal-Bench website or GitHub repository (reward hacking)". Maintainer merge, then automatic import. Closed 2026-05-14 pending a new process.
- The April 2026 "Leaderboard Integrity Update" added: ATIF trajectories required for all passing trials; reward hacking (e.g. curling solutions from the internet) → trial reward 0 by an agent judge, open-sourced so submitters can pre-check; cheating (timeout edits, encrypted solutions in the agent binary, uploading `tests/` during agent setup) → takedown. Named cases: OB-1/OpenBlock, Pilot/QuantFlow, ForgeCode.

For 4.0 (`prior/tb-leaderboard/leaderboard/`, designed per `SETUP.md` to be "vendored into any benchmark repo"):

| Piece | File | What it pins or checks |
|---|---|---|
| Dataset ref | `src/leaderboard/core/hub.py` (`DATASET@DATASET_REF`, a `sha256:` Hub digest) | every trial must have run this exact version; per-trial anti-tampering check |
| Trial count | `src/leaderboard/ci/static_analysis.py` (`EXPECTED_TASK_COUNT`, ≥ 5 trials per task) | errored trials count as reward 0 |
| Submission JSON | `submissions/<date>-<model>-<effort>-<agent>.json` | `source_jobs` (Hub job UUIDs), `source_filter{agent, agent_version, model_name, reasoning_effort}`, `metadata` (display links, model `release_date`), `metrics` (`accuracy`, `accuracy_ci95_half_width`, `n_trials`, `successes`, `pass_at_2..5`, `uncached_input_tokens`, `cached_input_tokens`, `output_tokens`, `total_tokens`, `total_cost_usd`, `avg_trial_duration_sec`), `disqualified_trials`, `trials` (UUID list). Example: `2026-09-02-anthropic-claude-fable-5-1-max-claude-code.json`: agent_version 2.1.257, 330 trials, 57.88 ± 3.76, $6,243.50, 2.75 B tokens. |
| Schema contract | `leaderboard.yaml` (`metadata_schema`, `metrics_schema`, `columns`, `rank_by`) | applied to the Hub leaderboard `terminal-bench/terminal-bench/4-0-0` |
| Maintainer run configs | `runs/tb-4-0-0-*.json` | Harbor job configs: dataset `terminal-bench/terminal-bench@v4.0.0`, `n_attempts 5`, agent `kwargs.version` pinned (e.g. claude-code 2.1.231), `reasoning_effort`, env such as `CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000`; launched with `harbor run --launch --org terminal-bench --config` |
| Workflows | `.github/workflows/leaderboard-{check,judge,apply,merge,recheck,close}.yml` | `pull_request_target` static analysis reads the JSON as data only; on green, CI clones the trials into leaderboard-owned copies (immutability) and opens a bot PR `submission/pr-N`; `/judge` runs the reward-hacking LLM judge on Modal over every passing trajectory (needs `trajectory_path`); `/apply` writes `disqualified_trials` and recomputes metrics (cost totals keep every trial); merge posts the row via a Hub edge function. |
| Task authoring rules | `CONTRIBUTING.md`, `docs/task-template.toml` (canary GUID comment, `environment_mode = "separate"`, `network_mode = "public"`), `scripts/checks/`, `docs/prompts/{task-proposal.md, task-implementation.toml, trial-analysis.toml, hack-trial-prompt.md}` | instruction must end with "You have N seconds to complete this task. Do not cheat by using online solutions or hints specific to this task."; ground truth lives only in the verifier image; PR CI runs oracle, nop, and "cheat" agent trials |

Versioning rule (`/news/continuous-benchmarks`): task patch → reuse trials; verifier-only change (separate container) → regrade; environment change → rerun; dataset version = max task bump; leaderboards bound to a dataset version; saturated tasks (5/5 by every frontier family) removed. 4.0 was a major bump because resource limits changed.

DOI status: Harbor and the TB repo each carry a Zenodo concept DOI in `CITATION.cff`. There is no DOI for a leaderboard submission, the HF submission dataset, or the Meta-Harness artifact.

### Design constraints implied for Repère (Terminal-Bench)

1. A per-paper frozen artifact must contain four things the TB pattern keeps in three different places: (a) the agent and harness code at a git tag with `uv.lock`; (b) the full job directory (job `config.json`, `result.json`, `lock.json`, every trial with `result.json`, ATIF `trajectory.json`, verifier logs, artifacts); (c) the task dataset at a content digest or commit; (d) the price table used. Deposit (a)+(b)+(d) as one Zenodo record with a concept DOI, and cite the dataset digest inside it.
2. The trial records must carry the code digest of what actually ran (Harbor's `TrialLock.task.digest` covers the task; add an `agent_code_digest`), so the artifact repo can be checked byte-for-byte; the Meta-Harness record cannot be.
3. Submission JSON schema: copy TB's `source_filter` (agent, agent_version, model_name, reasoning_effort) and `metrics` (accuracy, `accuracy_ci95_half_width`, `n_trials`, token split into uncached/cached/output, `total_cost_usd`, `avg_trial_duration_sec`, pass@k) and add `price_table_digest`, `pricing_date`, `harness_version`, `dataset_digest`, and a `data_window` field for the live-data tasks.
4. CI must reject: `timeout_multiplier != 1.0`, any `override_*`, any `extra_allowed_hosts`, incomplete task coverage, fewer than 5 trials per task, trials whose task digest differs from the pinned dataset, and passing trials without an ATIF trajectory. Errored trials count as reward 0; cost totals count every trial.
5. Run an LLM reward-hacking judge over every passing trajectory before a row is published, with a `disqualified_trials` list and a challenge path; for Repère the specific hack to detect is "agent found pre-processed or published values instead of fetching and processing raw observatory data".
6. Make submitted trials immutable by copying them into a store the submitter cannot modify (TB clones Hub trials; for Repère, a maintainer-owned bucket or the Zenodo deposit itself).
7. Semantic-version the tasks: patch = reuse, verifier change = regrade from artifacts, environment or data-window change = rerun; keep one leaderboard per dataset version; define a saturation rule for retiring tasks.
8. Calibrate timeouts and resources with a headroom run before freezing them (TB 4.0 moved to a flat 8 h agent timeout after measuring that timeouts drove errors); publish the calibration.
9. Put the canary comment in every `instruction.md` and the "do not cheat" suffix with the numeric timeout; keep ground truth only in the verifier image; add the Repère repo and any answer-bearing pages to the deny side of the allowlist.
10. Record model `release_date` and `reasoning_effort` as leaderboard columns, since TB's own rows differ by effort at fixed model.

### What Repère could adopt directly vs must build (Terminal-Bench)

| Adopt as is | Must build |
|---|---|
| The `leaderboard/` package (`lb filter|metadata|open-prs|submit`, `ci/static_analysis.py`, `ci/judge.py`, `ci/apply.py`, `ci/submit.py`, `ci/clone_trials.py`) and the six workflow files; `SETUP.md` is written for exactly this reuse | Replace the Harbor Hub dependency (`core/hub.py`, `HARBOR_API_KEY`, edge functions) with a self-hosted store, or accept the Hub; TB 2.0's HF-dataset-by-PR layout is the no-Hub fallback |
| `leaderboard.yaml` schema pattern (metadata_schema, metrics_schema, columns, rank_by) | Zenodo deposit step and DOI in the row (TB has none) |
| `docs/task-template.toml`, `scripts/checks/*.sh`, `docs/prompts/*` (task rubric, trial analysis, hack-trial prompt), `.github/harbor-run-defaults.yml` (oracle/nop/cheat trial CI) | Live-data pinning: recorded HTTP cassettes or dated data snapshots as task artifacts, and a `data_window` in the task metadata |
| Validation rules (timeout multiplier, no overrides, ≥ 5 trials, errored = 0, ATIF required) | Price provenance in metrics (pricing date, table digest) |
| Semantic-versioning and regrade policy | Judge rubric specialised to data-fetching shortcuts and RAG citation fabrication |
| `runs/*.json` pattern for maintainer-owned reference runs with pinned agent versions | |

---

## 3. HAL, Princeton (princeton-pli/hal-harness, arXiv:2510.11977)

### Metadata

| Item | Value | Source |
|---|---|---|
| Status | GitHub `archived: true`; README: "HAL leaderboard results are no longer being updated through this harness ... the repository is archived for historical reference"; `CONTRIBUTING.md`: no new results or PRs | GitHub API, `prior/hal-harness/README.md` |
| Last commits | `16bb03eb` 2026-07-01 "Document archived contribution status"; `481c1305` 2026-07-01 ReplicatorBench agent; `047a8e29` 2026-07-01 "Add GPT-5 family and o4-mini pricing (#167)" | GitHub API |
| Created / stars | 2024-07-29; 311 | |
| License | No LICENSE file; GitHub reports `license: null`. NOT VERIFIED what terms apply. | |
| Python / install | `requires-python >= 3.11` (README says conda python=3.12); `git clone --recursive` (13 submodules: SWE-bench fork, USACO, SWE-agent forks, Agentless, Moatless, SciCode, ScienceAgentBench, smolagents fork); `pip install -e .` plus extras `[swebench]`, `[azure]`, `[appworld]`, `[taubench]`, `[scicode]`, `[assistantbench]`, `[corebench,coreagent]`, `[open_deep_research]`, `[hal-agent-inspect]`; setuptools; version 0.1.0; no tags or releases | `pyproject.toml`, `.gitmodules` |
| CLI | `hal-eval`, `hal-upload`, `hal-decrypt` | `pyproject.toml` |
| Required env | `.env` with provider keys, `WANDB_API_KEY`, `HF_TOKEN`, `EXECUTED_BY` (mandatory "for tracking who ran the benchmark"), Azure fields | `.env.template` |
| Paper | arXiv:2510.11977 v1, 13 Oct 2025, 15 pp.; 21,730 rollouts, 9 models, 9 benchmarks, about $40,000; ICLR 2026 per site | `prior/hal_2510.11977.txt` |

### Agent runner

`prior/hal-harness/hal/cli.py` (click; options `--benchmark`, `--agent_dir`, `--agent_function module.fn`, `--agent_name "Name (model-with-date)"`, `-A k=v` agent args, `-B` benchmark args, `-I` Inspect args, `--max_concurrent`, `--max_tasks`, `--task_ids`, `--run_id`, `--continue_run`, `--ignore_errors`, `--task_timeout` default 2700 s, `--docker` (4 GB, 2 CPU per container), `--vm` (Azure), `--conda_env_name`, `--upload`, `--prompt_sensitivity`, `--num_variations`, `--variation_strength`, `--agent_version`). `validate_model_pricing()` exits if `model_name` is not a key of `MODEL_PRICES_DICT`.

`hal/agent_runner.py::AgentRunner`: `weave.init(run_id)`; dataset from `BenchmarkManager` (`hal/benchmark_manager.py`, 19 benchmark names); runners `LocalRunner` (conda), `DockerRunner`, `VirtualMachineRunner` (Azure, `hal/utils/vm/`); resume via `<run_id>_RAW_SUBMISSIONS.jsonl` (`get_remaining_tasks`); `weave.finish()` before `benchmark.evaluate_output()` "to avoid lm as judge to produce additional cost"; `benchmark.process_results()` writes `<run_id>_UPLOAD.json`.

Agent contract (`agents/README.md`): `agents/<name>/main.py` with `run(input: dict[task_id, task], **kwargs) -> dict[task_id, submission]` and a `requirements.txt`; "do not spawn new processes or threads that will not be logged by Weave"; deps must be compatible with `weave>=0.52.36`. Benchmark contract (`hal/benchmarks/README.md`, `base_benchmark.py`): subclass `BaseBenchmark`, implement `evaluate_output()` and `get_metrics()` returning at least `accuracy`, `successful_tasks`, `failed_tasks`; `_ground_truth_keys` stripped before tasks reach the agent; optional `requires_sandbox`, `setup_script`, per-task `gpu: true`, `files` dict copied into the agent cwd.

### Cost tracking

`prior/hal-harness/hal/utils/weave_utils.py`:

- `MODEL_PRICES_DICT`: hard-coded Python dict, one entry per model-id string (many aliases per model: bare, `openai/`, `anthropic/`, `openrouter/`, `bedrock/`, `together_ai/`), values `{"prompt_tokens": $/token, "completion_tokens": $/token}`. About 190 keys as of the final commit (through GPT-5.5, Opus 4.7, Gemini 3.5 Flash).
- `CACHED_PRICE_OVERRIDES`: per-model cache-read price; used for both cache creation and cache read; falls back to the prompt price.
- `_normalize_usage()`: maps OpenAI (`prompt_tokens`, `prompt_tokens_details.cached_tokens`), Anthropic (`input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`), and Bedrock (`inputTokens`, `cacheReadInputTokens`, `cacheWriteInputTokens`) shapes to (prompt, cached, cache_creation, completion).
- `get_total_cost(client)`: streams every Weave call's `summary.usage`, aggregates per model, computes `fresh_input * p_in + cache_creation * p_cache + cache_read * p_cache + completion * p_out`; models absent from the dict are silently skipped (a warning only in `get_task_cost`).
- No date or version field on prices. The paper fixes them in prose ("per-token costs as of September 24, 2025", Table A11) and admits SWE-Agent cache hits were charged at full price at submission time (A4.1).
- `compute_cost_from_inspect_usage()` prices Inspect `input_tokens_cache_read/write` at the full prompt price.

The `_UPLOAD.json` produced by `base_benchmark.py::process_results` holds: `config{agent_name, benchmark_name, date, run_id, agent_args, run_command, agent_version}`, `results{accuracy..., total_cost, latencies}`, `raw_eval_results`, `raw_logging_results` (per task: messages, per-call usage and timestamps, model, call_count), `task_prompts`, `total_usage`, `git_info` (commit), `agent_hash` (sha256 over the agent dir, `hal/utils/utils.py::compute_agent_dir_hash`), `wall_clock_times`, `task_step_counts`, optional `prompt_sensitivity_metrics`.

### Inspect AI integration

At the archived HEAD there is no `hal/inspect/` and no `hal/benchmarks/inspect_benchmark.py` even though the README still lists them; only `-I` flags, `is_inspect_solver()` in `cli.py`, and `compute_cost_from_inspect_usage` remain. The code was deleted in commit `5a07cf9f` (2026-01-28, "Remove agentharm, cybench, gaia, and dead blocks of commented out code (#142)", which also removed `agents/inspect/agentharm/...`). Read at the prior commit `3f0493b4` via the GitHub API:

- `hal/inspect/README.md`, `inspect.py`, `agent.py`, `hf.py`, `log.py`, `weave.py`; `hal/benchmarks/inspect_benchmark.py`.
- Benchmarks named `inspect_evals/<task>` or `inspect:<path>` were resolved with `inspect_ai._eval.loader.load_tasks` and `inspect_ai.model.get_model`; the Inspect `Task` supplied dataset and scorer only.
- Two agent modes: an `agent_function` whose return annotation is `Solver` was used as the Task's solver inside `inspect_ai.eval`; otherwise the external `run(tasks)` function received samples (`id, input, choices, target, metadata, files, setup`) and returned completions that Inspect then scored. Inspect's `.eval` log was written to the results dir and its metrics merged into `_UPLOAD.json`; GAIA per-level accuracy was computed from the Inspect log.
- So HAL used Inspect for datasets, scorers and the eval log, never for sandboxing or cost; cost still came from Weave or from Inspect usage counters priced with HAL's own dict.

### Weave / logging

Weave client per `run_id`; a `weave_task_id` attribute on each downstream call groups calls by task; `get_weave_calls()` reconstructs per-task message arrays from the call with the most messages plus per-call usage and timing, and per-task latency (first to last call). Paper A3 hurdle 12: a Weave bug blocked evaluation "for months". Commit `dd11885e` (2026-06-29) "align weave/gql pins with working versions" shows the pin churn continued to the end.

### Upload, traces, verified runs, repeats

- `hal-upload` (`hal/utils/upload.py`) zips `<run_id>_UPLOAD.json` plus `<run_id>_RAW_SUBMISSIONS.jsonl`, encrypts with `ZipEncryption` using the fixed password `"hal1234"` (in source), and uploads to HF dataset `agent-evals/hal_traces`; `hal-decrypt` reverses it. Purpose stated as avoiding benchmark contamination.
- Leaderboard (hal.cs.princeton.edu, per-benchmark pages such as `/corebench_hard`): columns Rank, Scaffold, Primary Model, Verified, Accuracy (with CI), Cost (USD), Runs, Traces. The site describes Verified as reproduced by the HAL team; external rows say "Submitted by <name>" (e.g. Nicholas Carlini's Claude Code runs on CORE-Bench Hard, 77.8%, "95.5% manual", $87.16). No code in the repo implements the flag; it is a website-side notion. NOT VERIFIED beyond the page text. Submissions are closed.
- Repeats: `hal-eval` has no repeat flag; one invocation is one run; "Runs" on the leaderboard counts submitted evaluations. The paper ran single runs (A3 hurdle 1: "we were forced to rely on single runs without statistical validation for most evaluations"). The later `reliability_eval/` package (`run_reliability_eval.py --n 5 --k`, phases baseline/fault/prompt/structural/safety/abstention) launches K identical `hal-eval` runs and computes outcome consistency `(2 p̂ − 1)^2` per task (`reliability_eval/metrics/consistency.py`), trajectory consistency by Jensen-Shannon distance over action distributions, robustness ratios (`accuracy_with_perturbation / baseline`), calibration, and safety scores. This is what the Reliability Dashboard (15 agents, 2 benchmarks, 12 metrics) reports. `hal-eval --prompt_sensitivity` also computes per-task variance across prompt paraphrases.

### Findings from the paper (read from the PDF text)

Cost and accuracy (Section 4.1):

| # | Finding | Numbers |
|---|---|---|
| 1 | Pareto frontier is steep | the most costly model is on the frontier in 1 of 9 benchmarks; Opus 4.1 $15/$75 vs GPT-5 $1.25/$10 per M tokens |
| 2 | Frontier is sparse | fewer than 1/3 of models on the frontier per benchmark; Gemini 2.0 Flash 7/9, GPT-5 4/9, o4-mini Low 4/9; DeepSeek R1 0/9; Sonnet 3.7 High 1/9; Opus 4.1 1/8 |
| 3 | Accuracy gains are not token-efficient | positive token-accuracy correlation on 6 of 9 benchmarks |
| 4 | Token-Pareto and dollar-Pareto disagree | Opus 4.1 on the token frontier 3/8 vs cost frontier 1/8; o3 price fell 80% since release |
| 5 | More reasoning is not better | 21 of 36 model-scaffold-benchmark pairs equal or lower accuracy at higher effort (Sonnet 3.7, Sonnet 4, Opus 4.1, o4-mini) |
| 6 | Scaffold dominates cost | Online Mind2Web: SeeAct + GPT-5 $171 vs Browser-Use + Sonnet 4 $1,577, 9x for 2 points |
| 7 | Generalist scaffolds lose accuracy | CORE-Agent beats generalist 9/12, SWE-Agent 11/12; generalist cheaper 20/24 |
| 8 | Benchmark cost spans orders of magnitude | ScienceAgentBench ≈ $13 per evaluation, Online Mind2Web > $450; Opus 4.1 on Mind2Web skipped at an estimated $20,000 |

Method notes: frontier drawn as the convex hull including the origin (randomised mixtures of agents are admissible); costs from per-token prices dated 2025-09-24; Anthropic "high" = LiteLLM's 4,096 reasoning tokens.

Log analysis (Section 4.2, Docent rubrics over 1,634 transcripts): agents found gold answers on HuggingFace or arXiv in 8 cases; hard-coded "plausible" outputs to pass unit tests; used a wrong credit card in a booking task; almost no run on SciCode or CORE-Bench without a tool-call failure; self-correction raises success 1.5x to 4x; explicit verification raises it 13% to 87%; instruction violations in > 60% of failed tasks on AssistantBench and CORE-Bench; environmental barriers in about 40% of failed tasks; the TAU-bench few-shot scaffold shipped with benchmark examples in its prompt (data leakage) and was dropped.

Reproducibility failures and model-version drift (Appendix A3, twelve hurdles): (1) cost blocks confidence intervals; (2) Together AI swapped DeepSeek R1 for R1-0528 behind the same endpoint on release day; (3) OpenAI removed the `stop` argument for o3/o4-mini and broke scaffolds; (4) OpenRouter served FP4 or FP8 quantizations per call by default; (5) rate-limit errors become silent false negatives; (6) Anthropic $5,000/month default spend cap; (7) LiteLLM gated reasoning support on an o-series regex; (8) reasoning effort levels not comparable across providers; (9) parameter formats differ per provider for the same model; (10) benchmark instructions entangled with scaffold instructions; (11) frozen dependencies vs constantly changing providers; (12) an upstream Weave bug blocked evaluation for months. A4 adds: cache hits not priced; public test sets used for GAIA and AssistantBench; latency unreliable under parallel execution.

Explicit recommendations (Conclusion and Table 2): systematic log analysis as a mandatory leaderboard component; standardised infrastructure instead of per-benchmark reimplementation; report tokens, failure modes and scaffold interactions, not accuracy alone; separate the harness environment from the agent environment to freeze benchmark dependencies; document exact model versions and reasoning settings (agent names of the form "Name (model-with-date)"); report both dollar and token Pareto frontiers because prices move.

### Design constraints implied for Repère (HAL)

1. Cost must be computed from a checked-in table keyed by exact model id with separate uncached-input, cache-write, cache-read and output prices (HAL's `MODEL_PRICES_DICT` + `CACHED_PRICE_OVERRIDES`), extended with an `effective_date` and a table version; the run must refuse to start if the model id is absent (`validate_model_pricing`), and must never silently skip an unpriced model as `get_total_cost` does.
2. Every reported run names the dated model snapshot, the provider endpoint used (direct API vs aggregator), and the reasoning-effort setting in provider-native units; runs through aggregators that route across quantizations are excluded from headline numbers.
3. Repeat every configuration K ≥ 5 times and report mean ± CI and per-task outcome consistency `(2 p̂ − 1)^2`; Repère's tasks are cheap enough that HAL's excuse (cost) does not apply.
4. Infrastructure failures (rate limits, data-service outages) must surface as a distinct status, never as reward 0 by default; the report shows an error rate column next to accuracy (HAL hurdle 5; TB counts them as 0, which is fine for a leaderboard but hides infra noise in a paper).
5. Run a rubric-based LLM log analysis over every trajectory with at least HAL's six categories (instruction violation, tool-use failure, self-correction, verification, environmental barrier, shortcut/gaming), plus Repère-specific shortcuts: fetching published derived products instead of raw data, fabricating citations, answering metadata questions from parametric memory instead of the catalogue.
6. Freeze the harness environment and each agent environment separately (`uv.lock` for both) and record `git_info`, `agent_hash` (sha256 of the agent directory), and the exact `run_command` in every result file, as HAL's `_UPLOAD.json` does.
7. Log every LLM call with usage and timestamps keyed by task id to a local JSONL under the harness's control; do not make a hosted tracing service a hard dependency (hurdle 12).
8. Keep task instructions and scaffold prompts in separate files (hurdle 10) so a prompt change never touches the task digest.
9. Report both a dollar Pareto frontier and a token Pareto frontier, drawn as a convex hull including the origin, and re-price old runs from stored token counts when the price table changes.
10. Maintain a `verified_by` field: a row is verified only when a Repère maintainer reruns it from the DOI artifact; unverified community rows are shown but labelled.

### What Repère could adopt directly vs must build (HAL)

| Adopt as is (copy the code, not the harness) | Must build or replace |
|---|---|
| `MODEL_PRICES_DICT` / `CACHED_PRICE_OVERRIDES` structure and `_normalize_usage()` for OpenAI, Anthropic and Bedrock usage shapes (`hal/utils/weave_utils.py`) | Dated, versioned price table with a digest; a re-pricing tool over stored token counts |
| `validate_model_pricing()` fail-fast | Everything about execution: HAL's runners are conda, Docker (fixed 4 GB/2 CPU) and Azure VMs, with no network policy and benchmark-specific submodules; use Harbor instead |
| Consistency, robustness and calibration formulas in `reliability_eval/metrics/` and the K-repetition driver pattern in `run_reliability_eval.py` | Weave replacement (local JSONL from ATIF) |
| `_UPLOAD.json` field set: `git_info`, `agent_hash`, `run_command`, `wall_clock_times`, per-task latency | Trace publication without a hard-coded password; use canary strings, gated access and a DOI instead |
| Docent rubric categories (Table A5) as judge prompts | Inspect AI integration if wanted: HAL's was removed in January 2026, so nothing to reuse; Harbor's RewardKit or `harbor analyze` covers judging |
| Prompt-sensitivity mode (`--prompt_sensitivity`, `hal/utils/prompt_variation.py`) as an optional robustness phase | |
| Agent naming convention "Name (model-with-date)" | |

---

## 4. Cross-cutting summary for the Repère design

| Requirement | Harbor gives | TB adds | HAL adds | Repère must build |
|---|---|---|---|---|
| Accuracy jointly with dollars | per-trial `cost_usd` (LiteLLM or agent self-report), job totals | `total_cost_usd`, token splits, CI in submission JSON | dated price dict, cache tiers, dollar and token Pareto | owned price table with date + digest; recompute from ATIF; store reported and table costs |
| Repeats and variance | `-k`, pass@k | ≥ 5 trials rule, `accuracy_ci95_half_width` | consistency `(2p̂−1)^2`, robustness phases | default K=5, per-task consistency, infra-error column |
| Pinned model versions | `model_info{name, provider}`, `agent_info.version` | `source_filter.agent_version`, `reasoning_effort`, `release_date` | naming rule, drift catalogue | dated-snapshot validator; provider endpoint field; aggregator exclusion |
| Frozen artifact while harness evolves | `lock.json` (task digest, harbor version + commit), regrade | agent repo + immutable trial store + submission JSON + semantic versioning | `agent_hash`, `git_info`, encrypted traces | Zenodo packager with concept DOI; agent-code digest in trial lock; `uv.lock` per artifact |
| Live network tasks | allowlist per phase, egress sidecar, capability check | open-internet policy, judge for online solutions | shortcut detection via logs | host allowlists for OOI M2M, FDSN and portals; HTTP cassettes or dated snapshots; data-window field |
| RAG agents | external `BaseAgent`, RewardKit judges | none | none | RAG wrappers; citation verifiers against a frozen index |

Recommendation: build Repère as a Harbor dataset plus custom agents, vendor the Terminal-Bench `leaderboard/` package for submissions and judging, and copy HAL's price-table and reliability-metric code into a small `repere` package that owns pricing, re-pricing, consistency statistics, and the Zenodo packager.

## 5. NOT VERIFIED list

| Item | Why |
|---|---|
| HAL harness license | no LICENSE file; GitHub API `license: null` |
| Harbor version that produced the Meta-Harness 76.4% run | not recorded in the submitted `config.json`/`result.json`; `pyproject` only says `>=0.1.44` |
| Whether the Meta-Harness row still displays on tbench.ai | site front page now shows 4.0; the 2.1 leaderboard URL was not retrieved |
| Semantics of HAL's "Verified" column beyond the page text ("reproduced by the HAL team") | no code path; website only |
| Whether `--agent-import-path` (used in the artifact README) still works on Harbor 0.23 | docs now show `-a module:Class`; not tested |
| The TB 2.0 leaderboard's server-side importer and the new post-May-2026 2.x submission process | HF README says "check back by end of June"; nothing found |
| Exact Harbor 0.23 CHANGELOG entries on `lock.json` introduction | grep found no `lock.json` mention in the top of the changelog; the model and viewer tab exist |

## Note on the requested output file

The harness blocked writing `<scratch>/report_prior_harbor_tbench_hal.md` (subagents may not write report files). The content above is the complete report; the caller can save it to that path verbatim. The source clones and the extracted HAL paper text remain under `.../scratchpad/prior/`.