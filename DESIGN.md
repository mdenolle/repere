# FrugalMind-RCA: design and architecture decision memo

Status: draft for review, 2026-09-14. Branch `design/rca-harness`. Nothing
in this document is a benchmark result; every record in the suite is a
template until a named person verifies it (`docs/rca/AUTHORING.md`).

Companion documents: `docs/rca/00_frugalmind_inventory.md` (what the repo
already contained), `docs/rca/ABC_AUDIT.md` (Agentic Benchmark Checklist
audit), `docs/rca/AUTHORING.md` (record authoring rules), `OPEN_QUESTIONS.md`
(decisions that need Marine), `docs/rca/prior_art/` (reading notes with
file and line references for every claim about external systems).

## 0. Names

| Term | Use it for | Do not use it for |
|---|---|---|
| FrugalMind | the harness (this repository) | the RCA suite alone |
| FrugalMind-RCA | this suite: three agent families serving the OOI Regional Cabled Array | |
| GAIA HazLab | the lab and its GitHub organisation; always two words, never bare "GAIA" in a paper that also cites agent benchmarks | |
| the GAIA benchmark (Mialon et al., 2023) | the general-assistant benchmark, cited in full at first mention | |
| aRCADA | mhemmett/arcada, the public assistant over the RCA | the RCA data itself |
| chronfix, chronos | chronfix applies clock corrections; chronos (not public) measures them | one word for both |

Recommendation for the paper: first mention reads "GAIA HazLab (the University
of Washington hazards lab; unrelated to the GAIA benchmark of Mialon et al.,
2023)", and the harness is never called "GAIA eval". The sibling private repo
`mdenolle/gaia-eval` should be renamed before anything public references it
(proposal: `hazeval`); see OPEN_QUESTIONS.md Q1.

## 1. What this adds to frugalmind

frugalmind at `main@8db9914` is an Inspect-based harness with six suites,
a subprocess or Docker sandbox, JSONL telemetry, a skill system, a Pareto
leaderboard and a manuscript (inventory in `docs/rca/00_frugalmind_inventory.md`,
test suite rerun today: 317 passed, 7 skipped). It has no OOI content, no
frozen price map with dates, no repeats, no model-version pin check, no
lexical baseline, no judge calibration, and no per-paper frozen artifact.

FrugalMind-RCA adds, under `src/frugalmind_suites/rca/`:

| Piece | File | State |
|---|---|---|
| Golden-record schema (shape A and B, explicit tier) | `schema/golden_record.schema.json` | done |
| Validator: JSON Schema plus 15 cross-field rules R01 to R15 | `validate.py` | done, 16 seeds pass, `--strict` fails templates |
| 16 seed records, all `status: template` | `seeds/{coding,litreview,sensor}/` | done; every one carries co-author TODOs |
| Frozen price map with versions and verification flags | `pricing/prices.yaml` | skeleton; Anthropic rates from two written sources that disagree on Opus 4.6; all other providers TODO |
| Cost layer: price a run, flag unpinned models and unverified prices | `cost.py` | done |
| T2 deterministic checkers with staged scoring | `checkers.py` | done |
| T1 oracle (chronfix clock offset and triggers) | `oracles/clock.py` | done; interval F1 not yet |
| Inspect task and tier-dispatching scorer with void taxonomy | `inspect_tasks.py` | done for T2, T1 numeric, T3; T4 refuses by design |
| Runner: repeats, cost, reliability, logged result | `run.py` | done; end-to-end verified with scripted solvers |
| Baselines: do-nothing, BM25-only | `solvers.py`, `baselines.py` | done |
| Fetch script for pinned external inputs | `scripts/rca_fetch_external.py` | done; verified today |
| Sandbox: stage input files | `sta_lta/sandbox.py` (`input_files=`) | done, additive, existing tests pass |
| Record/replay proxy | `data/public/cassettes/README.md` | design only |
| OOI M2M and station-metadata tools | | proposed (§5.2) |
| Judge calibration path | | refused until built (§4.4) |
| Zenodo packager | | proposed (§5.4) |

## 2. Task taxonomy

Three agent families and seven task groups, transcribed from the whiteboard.
Two board items were unreadable and are not filled in (OPEN_QUESTIONS.md Q2,
Q3).

| Family | Group | What the agent must produce | Tier | Shape | Seeds |
|---|---|---|---|---|---|
| 1 coding | 1a download and processing | resolve a plain-language request to OOI M2M, EarthScope FDSN or a PI portal and emit a script that runs and returns the records | T2 | B | `rca-coding-download-hys14-bhz-001`, `rca-coding-download-m2m-prest-001` |
| 1 coding | 1b QC | gaps, overlaps, coverage; clean windows are first-class negative cases | T2 | B | `rca-coding-qc-continuity-001` (control) |
| 1 coding | 1c calibration and timing | clock offset at an hour; resync detection | T1 | B | `rca-coding-timing-offset-hys14-001`, `rca-coding-timing-resyncs-hys14-002` |
| 1 coding | 1d coding plus tool calls | STA/LTA with given parameters via `python_session` | T2 | B | `rca-coding-stalta-hys14-001` |
| 2 lit-review | 2 | which papers used a sensor; grounded answers with citations; abstention after the cutoff | T3 | A | five `rca-litreview-*` |
| 3 sensor | 3 | which channel; data availability; what a sensor is; known issues; photos with credit | T3, T4 | A | five `rca-sensor-*` |

Board note "data: nc ... python" under 1d: unread, see Q2. The model row on
the board (Claude, OpenAI, Gemini, Olmo, Qwen, Kimi, Mistral) is the sweep
axis; the price map has one provider block per name, all but Anthropic and
local marked TODO (§6.2).

Knowledge base on the board, "chunked, papers, figures, photos": the chunk
and paper layers exist in aRCADA (`public/chunks.json`, 802 chunks; 142
papers; 18 full-text PDFs). Figures and photos do not exist anywhere in the
repos and are treated as a separate corpus with licence fields (§3.3).

## 3. Verification tiers

### 3.1 Definitions and mapping to frugalmind's scorability spectrum

frugalmind already orders scorers T0 deterministic, T1 numerical, T2
perceptual, T3 trajectory, T4 rubric (`docs/dataset_submission.md` §4). The
RCA tiers are organised by *how truth is established*, not by scorer type,
so the two vocabularies coexist and every RCA record names its scorer method
explicitly. To avoid the collision the RCA tier names carry a suffix:

| RCA tier | Truth comes from | Scorer method (record field) | frugalmind scorer tier | Metric |
|---|---|---|---|---|
| `T1_physics` | an independently measured physical quantity with an oracle solver | `oracle_compare` | T1 numerical | absolute error, within-tolerance, F1 for intervals |
| `T2_execution` | executing the generated code and checking the result deterministically | `execution_check` | T0/T1 | staged pass/fail 0.1 code, 0.2 runs, 0.7 correct |
| `T3_reference` | a date-bounded reference corpus and human-graded relevance | `retrieval_metrics`, `citation_support`, `exact_match` | T0 | nDCG@k, recall@k, citation precision and recall, abstention |
| `T4_judgment` | an expert rubric | `rubric_judge` | T4 | rubric mean, reported only with agreement statistics |

Void versus fail (ABC T.3): when the harness cannot score for a reason that
is not the agent's fault, the sample is `void` with a reason and excluded
from aggregates; the runner prints the count. A zero without `void` is a
real failure. Reasons implemented: network policy not satisfiable, input
hash mismatch, oracle has no reference at that hour, checker exception,
judge not calibrated.

### 3.1c What the T1 oracle really is

The whiteboard says clock error is "independently measurable by
ambient-noise cross-correlation" and that chronfix/HYS14 "gives us an
oracle". Reading the repo (`docs/rca/prior_art/coszo_chronfix.md`) narrows
that claim:

| Fact | Source |
|---|---|
| chronfix only *applies* corrections; the measurement code (chronos) is not public | chronfix README.md:5-7; no chronos repo in coszo-hub |
| the delivered reference is `delta_t_hourly_clean.npy`: 31,563 hourly values, 2022-08-10 to 2026-05-01, Hampel-filtered and segment-modelled | examples/HYS14/, Correction Method sections 4 to 6 |
| it is measured against HYS12, whose timing is asserted good and not demonstrated | Correction Method lines 30-31 |
| the validation is closed-loop: same pair, same band, same method | Correction Method lines 323-350 |
| stated precision: sigma_total 0.08 s typical, 0.11 s p90, 0.17 s worst; picker quantum 0.125 s at 8 Hz | README.md:150-164 |
| raw hourly peak-lag arrays are not shipped, only the cleaned series and figures | Correction Method lines 79-88, 122-128 |
| HYS12 has no BHZ: it is a CMG-6TF short-period with EHZ 200 Hz, SHZ 40 Hz, MHZ 8 Hz; chronos used MHZ | EarthScope station service, 2026-09-14; Correction Method line 40 |

So T1 is "physics-verified" in the sense that the ballistic lag between two
fixed stations cannot drift and the reference was produced by a different
pipeline than the agent's, but not in the sense of a GPS or PPS measurement.
The design keeps the tier and states the caveat in every T1 record's
`independent_measurement` field. Three ways to strengthen it are listed in
OPEN_QUESTIONS.md Q7 (HYSB1 cross-check, teleseismic arrival times against
TauP predictions, a post-2026-05 window with a fresh chronos run held
privately).

Tolerance: the seed uses 0.5 s absolute, four times the authors' typical
sigma. It is a placeholder for the timing co-author (Q7).

### 3.2 Corpus date cutoff (the drifting paper index)

Problem: aRCADA's paper index is a Zotero export (142 entries) with
year-only dates, rebuilt only from the authors' local library, with no
bibliographic API and no date filter (`docs/rca/prior_art/arcada.md` §5.2).
The index will grow; a T3 item scored today and a year from now must see the
same corpus.

Mechanism, modelled on AstaBench's three-layer enforcement
(`docs/rca/prior_art/astabench_agenteval_inspect.md` §1b):

1. **Snapshot pin.** Every T3 record carries `corpus_snapshot = {corpus_id,
   snapshot_ref}` where `snapshot_ref` is the aRCADA commit plus the file's
   sha256; the fetch script refuses a mismatch. Records also carry
   `cutoff_date`. The validator enforces both for T3 (rule R05).
2. **Tool-side filter.** frugalmind's `literature_search` already drops
   documents published after `cutoff_date` before ranking
   (`src/frugalmind/agents/literature.py:157`). Two additions from AstaBench
   are required: filter nested citation lists in results, and raise a tool
   error on a direct fetch of a post-cutoff id.
3. **Scorer-side re-check.** `retrieval_leakage` (already in
   `literature.py:181`) audits submitted ids for post-cutoff or fabricated
   ids; the RCA scorer records `cited_negatives`.
4. **Rebuild with real dates.** Replace the year-only index with one built
   from OpenAlex or Crossref for the same DOIs, adding `published` (full
   date) and `indexed_at` (the snapshot date); the cutoff then works at day
   granularity instead of year. Script to write: `scripts/rca_build_corpus.py`
   (Q4 for the source of truth: Zotero collection vs a DOI list).
5. **Temporal negatives.** Items whose correct answer is "nothing before the
   cutoff" (`rca-litreview-abstain-after-cutoff-004`) make the cutoff
   testable.

Provider-native web search cannot be date-bounded (only Perplexity accepts a
filter); it is banned from the Standard tooling class and classified Fully
custom if used.

### 3.3 Sensor knowledge base

Nothing in the repos is a sensor knowledge base yet. Proposed sources, each a
separate snapshot with its own id and licence field:

| Source | Content | Access |
|---|---|---|
| aRCADA `catalog/instruments.json` | 120 hand-curated entries, no provenance fields, several verified errors (stream names, missing FDSN station codes) | public, licence unstated |
| EarthScope station service (level=channel) | authoritative channel codes, rates, sensor descriptions, epochs | public API; snapshot as text |
| OOI M2M `/12587/events/deployment/inv` and `/12587/asset/cal` | deployments and calibration per reference designator | needs API token |
| OOI M2M `/12580/anno/find` | annotations (known issues) | needs API token |
| chronfix README and method doc | known timing issue on HYS14 | public, MIT |
| coszo.org `data_channels.csv` | COSZO station channel table | public |
| instrument-class pages, PI pages | prose descriptions | public web; snapshot |
| photos | | none yet; every entry needs `license`, `attribution`, `permission_status` before use |

### 3.4 The catalog-leakage problem and the holdout construction

aRCADA's instrument catalog is both the sensor agent's retrieval corpus and
the obvious source of items, so a catalog-derived question is trivially
solvable by lookup. The schema makes the mitigation an explicit field,
`holdout.construction`, and the validator (R09) refuses any item sourced
from the catalog or paper index without one:

| Construction | Rule | Example |
|---|---|---|
| `catalog_perturbed` | the gold differs from the catalog by a verified fact | availability date 2017-08-11 at EarthScope vs catalog 2015-04-01 |
| `catalog_excluded` | the referenced entry is removed from the snapshot the agent sees for that item (`corpus_snapshot.excluded_ids`) | ask about an instrument the catalog does not describe |
| `cross_source_join` | answer needs a source outside the corpus | HHZ 200 Hz channel, M2M vs FDSN routes, chronfix timing |
| `temporal_after_index` | content after the snapshot; correct answer is abstention | COSZO CZ* stations |
| `held_out_site` | a whole site is excluded from the corpus | reserved for the test split |
| `paraphrase_only` | prompt paraphrases a catalog field | allowed on validation only; never on test (R08) |

Mechanical leakage test: the BM25-only baseline (`baselines.py`) is run on
every split. An item the lexical baseline answers at better than chance on
the test split is leaked and goes back to authoring. This turns the
non-agentic control into the leakage detector.

## 4. Golden-dataset schema

Full schema: `schema/golden_record.schema.json`. Summary:

| Field | Required | Notes |
|---|---|---|
| `id`, `family`, `group`, `tier`, `shape`, `status` | all | id pattern `rca-<family>-<slug>-NNN`; status template, draft, verified, frozen, retired |
| `prompt` | all | must not contain the answer or checker logic (R12) |
| `provenance` | all | author, role, date, source, `source_ref`, `source_kind`, `verification` block |
| `holdout` | all | split, visibility, construction, leakage note, canary |
| `cutoff_date`, `corpus_snapshot` | T3 and any retrieval | R05 |
| `reference_output`, `reference_citations` (graded 0 to 3) | shape A | |
| `tools.allowlist`, `inputs.files` (sha256), `task`, `sandbox` | shape B | R07; `sandbox.image_digest` required before `frozen` |
| `scoring.method` plus one of `oracle`, `checker`, `reference`, `judge` | all | R02 to R06 |
| `photos[]` | family 3 when images are shown | licence and attribution required (R14) |
| `todos[]` | all | templates need at least one; verified and frozen need zero (R10) |

Shape A is "prompt plus reference output text"; shape B is "prompt plus
{tools, input files} plus task", matching the board. Every record also
carries the five minimum fields the brief asked for (stable id, family, tier,
provenance, held-out flag) plus the scoring method.

## 5. Architecture decision memo

### 5.1 Build versus adopt

Decision: keep Inspect AI as the evaluation loop and log substrate (already
adopted in frugalmind 0.4.0; the substrate of HAL and AstaBench), borrow
specific pieces from Harbor, agent-eval, HAL and Terminal-Bench, and build
the parts none of them has.

| Concern | Decision | Reason (source in `docs/rca/prior_art/`) |
|---|---|---|
| Eval loop, logs, epochs, model providers | **adopt Inspect** (`.eval` logs with `revision`, `packages`, per-sample `model_usage`, `total_time`, `working_time`; `Epochs`; `ModelCost`) | frugalmind already runs on it; HAL's Inspect integration was deleted in 2026-01, AstaBench's is a thin layer over it; verified today with a mock run |
| Container execution and egress control | **borrow Harbor's design, not its runtime**: allowlist per phase, egress proxy sidecar, separate verifier environment | Harbor needs Python 3.12, breaks on minor releases (v0.18 to v0.23 in ten weeks), phones home by default, and its Hub is a hosted service; the sidecar idea is what we need for §5.3 |
| Task-directory format | **export, do not author**: records stay YAML; a converter emits Harbor task dirs (`instruction.md`, `task.toml`, `tests/`) when a task must run under Harbor or be submitted to a Harbor dataset | keeps one source of truth; Harbor tasks import nothing from the harness so the export is cheap |
| Price map | **build** a dated, versioned, verified-flagged map (`pricing/prices.yaml`) | AstaBench's litellm pin is undated and had to be hand-patched; HAL's dict has no date; Harbor has no table at all |
| Cost per sample | **build** `cost.py`; later also register Inspect `ModelCost` so `cost_limit` works | Inspect's number depends on what was loaded at run time; the published number must be recomputable from tokens |
| Judge-token exclusion | **adopt agent-eval's span rule** (TODO; today by model id) | RAG judges may share a model with the agent |
| Openness and tooling vocabulary | **adopt agent-eval's seven strings** (frugalmind already has `openness`; add `toolset` values) | cross-leaderboard comparability |
| Pareto frontier | **adopt** the cost-ascending, score-descending sweep frugalmind already has; add CI on both axes at aggregate level | AstaBench has task-level CI only |
| Repeats and reliability | **build** in `run.py`: epochs, per-record mean, sd, pass rate, all-pass, bootstrap CI over records | none of the four prior systems aggregates across repeats; HAL's `(2p-1)^2` consistency is worth adding |
| Trivial baselines | **build** `do_nothing`, `bm25_only`; retry-until-pass and escalation as later conditions | AAM and ABC R.13 |
| Submission bundle and CI rules | **adopt Terminal-Bench's** `source_filter` and `metrics` fields, the five-trials rule, "errored trials count as 0, cost counts every trial", and the reward-hacking judge idea | see §5.4 |
| Hidden split hosting | **keep frugalmind's** Mode A (derive from secret) / Mode B (gated host) policy | `docs/golden_data_provisioning.md` |

### 5.2 Where the sandbox boundary sits

Three processes, three trust levels:

| Process | Holds | Network |
|---|---|---|
| Harness (Inspect, scorer, oracle, price map) | reference data, oracle inputs, model API keys, OOI token | model providers; live services only in record mode |
| Harness-owned tools (`fdsn_get_waveforms`, proposed `fdsn_get_stations`, `ooi_m2m_get`, `pi_portal_get`, `literature_search`, `sensor_kb_search`) | credentials, cutoff enforcement, cassettes | allowlisted hosts, recorded |
| Sandbox (model-generated code) | staged input files only | `none`, or the replay proxy |

Rules: credentials never enter the sandbox (frugalmind invariant 2 in
`docs/golden_data_provisioning.md`); reference values never enter the
sample metadata (`inspect_tasks.public_view`); the checker runs in the
harness, never in the sandbox; the sandbox image is pinned by digest before a
record is frozen (R10). The existing frugalmind sandbox is a robustness
boundary, not a security boundary (its own docstring); the Docker backend
with `--network=none` is the minimum for any reported number, and the host
backend is for development only.

### 5.3 Record and replay of live network calls: decision

The tasks make live calls to OOI M2M, EarthScope FDSN and PI portals.
Options considered:

| Option | Reproducible | Measures the real thing | Cost per rerun | Verdict |
|---|---|---|---|---|
| Live only | no: Terminal-Bench 2.1 found 9 of 89 tasks broken by external drift; OSWorld 13 of 46 | yes | network and rate limits every run | rejected as the scored default (ABC T.6) |
| Harness tools only, sandbox offline (frugalmind today) | yes for tool outputs | no: 1a's deliverable is a script that fetches | low | keep for 1b, 1c, 1d |
| Record and replay through a proxy | yes, with cassette hashes | yes in record mode; replay re-executes the agent's own request | low after recording | **chosen** |
| Pre-fetched data bundles per task | yes | no: bypasses the fetch | low | used only where data volume forbids replay (T1 resync item) |

Decision: **record once, replay as the scored default, re-record on a
schedule as a separate labelled live track.**

Argument. (1) The correctness signal in 1a is "the script returns the
requested records"; replay preserves that signal because the script still has
to form the right request, and a wrong request misses the cassette and fails.
(2) The drift the live track measures is a property of the services, not of
the agent; reporting it separately (a "drift report" per re-recording) is
more informative than letting it leak into agent scores (ABC R.9). (3) OOI
credentials stay in the proxy, so the sandbox never sees them; in replay mode
no credential exists in the run at all. (4) Replay makes repeats and GEPA
loops affordable and deterministic (§5.5).

Costs accepted: a proxy with a CA certificate in the sandbox image; a
cassette format with a canonical request key (`data/public/cassettes/README.md`);
one-time recording runs that need an OOI token; asynchronous M2M (NetCDF via
THREDDS) needs request-level matching because job URLs are not stable.
Not implemented in this session: the scorer voids `network: replay` records
with an explicit reason, and refuses `allowlist` records unless
`--allow-live-network` is passed and the rows are flagged.

### 5.4 A frozen, DOI-archivable artifact per paper while the harness moves

Pattern (Terminal-Bench separates agent repo, immutable trial store and
submission JSON; Harbor's `lock.json` records task digests and harness
version; HAL's `_UPLOAD.json` records `agent_hash` and `run_command`):

1. Tag the harness: `git tag paper/<short-name>-v1` on the commit used, with
   `pixi.lock` committed. `EvalSpec.revision` in every Inspect log already
   records commit and dirty flag; a dirty tree is refused for a paper run.
2. Freeze the suite: the exported JSONL of all records in the paper's split
   with `manifest.json` sha256 (existing `export.py`), the private split's
   hashes only, the price map file at its version, cassette hashes, sandbox
   image digests, and the ABC audit table as of that day.
3. Freeze the results: for every (agent, model, condition) row the `run.py`
   output (`summary.json`, `samples.jsonl`, the Inspect log) plus a
   submission JSON with Terminal-Bench's fields (`source_filter`: agent,
   agent version, model id, reasoning effort; `metrics`: accuracy, CI half
   width, n trials, token split, total cost) extended with
   `price_map_version`, `harness_tag`, `suite_manifest_sha256`,
   `sandbox_image_digest`, `data_window`.
4. Deposit 1 to 3 as one Zenodo record with a concept DOI (the harness
   already has `CITATION.cff`; enable the Zenodo GitHub integration so each
   `paper/*` tag also mints a version DOI). Reference data that we do not own
   (aRCADA catalog, chronfix files, OOI data) are cited by commit, hash and
   URL, not redistributed, unless licence permits (Q5).
5. The harness keeps moving: results are never rescored against a newer
   price map without a re-pricing run from stored tokens, and a leaderboard
   is bound to one suite version, as Terminal-Bench binds a leaderboard to a
   dataset version.

Tooling to write: `scripts/rca_freeze.py` (steps 2 and 3, produces the
deposit directory) and a CI check that a `paper/*` tag has a clean tree and a
verified price map.

### 5.5 GEPA

What GEPA requires of a task suite (`docs/rca/prior_art/papers_aam_abc_gepa.md` §3,
repo at 15ee314, v0.1.4, MIT, Python 3.10 to 3.14):

| Requirement | Our answer |
|---|---|
| a scalar score per example, higher is better, normalised to [0, 1] with `perfect_score` | every RCA scorer returns [0, 1]; graded rather than binary where possible (staged T2, nDCG T3) |
| feedback text per example, passed verbatim to the reflection model | to add to each scorer: residual and tolerance (T1), checker diff, stderr tail, replay-miss key (T2), hits, misses and post-cutoff ids (T3); T4 feedback is judge rationale and is excluded until calibrated |
| train, validation (Pareto selection) and a test set the optimiser never sees | three-way split field on the record set (`holdout.split` gains `gepa_train`, `gepa_val` values, or a separate manifest; Q8); the test split answers must differ in the *values* (instruments, windows, papers), because gold flows into the reflection prompt |
| budget in metric calls; reflection LM cost | `max_metric_calls` about 15 to 30 times the validation size; count sandbox executions as metric calls; report optimisation spend as fixed cost separately from per-task cost |
| deterministic evaluation | replay track only; never optimise on the live track |
| multi-component prompts | keep the agent prompt as named components (`system`, `data_access_rules`, `citation_policy`, `answer_format`) |

Stance: do not commit to GEPA until (a) the replay track exists, (b) at
least 30 verified records per family exist, and (c) an audit script greps
optimised prompts for gold values, instrument ids and citation ids from the
train and validation sets (an AAM shortcut and an ABC T.5 leak if found).

## 6. Evaluation and reporting

### 6.1 Per-run logging (implemented: `rca.result.v0.1`)

Each `samples.jsonl` row carries: record id, epoch, tier, record status,
score or void with reason, stage breakdown, model requested and model
reported by the provider, pin flag, price card and price map version,
cost-unverified flag, input, output, cache-read and cache-write tokens,
dollars, wall-clock and working time, tool-call and tool-error counts,
submitted flag, and a pointer to the Inspect log and sample uuid (the full
trace). `summary.json` carries the run header (git revision and dirty flag,
package versions, sandbox backend and image, price map version, flags) and
the aggregates.

### 6.2 Frozen price map

`pricing/prices.yaml`: USD per million tokens, one card per model with
`pinned_ids`, `verified`, `source_url`, `source_date`, `verified_by`. Rates
are never edited in place; the file version is bumped and old entries kept.
The runner refuses to price an unverified card unless
`--allow-unverified-prices` is passed, and then flags the row. Today every
card is unverified; the Opus 4.6 discrepancy (15/75 in `config/models.yaml`
dated 2026-05-08 versus 5/25 in a 2026-06-24 table) must be resolved by a
person before any Pareto plot is drawn (Q6). Local models cost 0 by
frugalmind convention; their pin is the weights digest, which the runner
does not yet record.

### 6.3 Model-version pinning

A row is pinned when the requested id is in a card's `pinned_ids` and the id
the provider reports back is the same or also pinned. Inspect records the
provider-reported id per call (`ModelOutput.model`; provider-dependent, see
`docs/rca/prior_art/astabench_agenteval_inspect.md` §3). Unpinned rows are
scored, flagged `model_unpinned`, rendered hatched on the leaderboard, and
refused on the test split.

### 6.4 Repeats and reliability

`--epochs k` (default 1, paper runs 5): per record mean, sample sd, pass rate
at a threshold, all-pass; suite mean of record means with a bootstrap 95%
interval over records; consistency as the fraction of records that pass in
every epoch. Voids are excluded and counted. To add: HAL's per-task outcome
consistency `(2p-1)^2`, and Inspect's `Epochs(k, ["mean", "collect"])` so the
`.eval` log carries the raw per-epoch values.

### 6.5 Baselines

| Baseline | Implemented | Role |
|---|---|---|
| do-nothing | `solvers.do_nothing` | ABC R.13; must score 0 on every non-void item |
| BM25-only over the catalog or paper index | `baselines.bm25_only` | the non-agentic control (aRCADA's own retriever is MiniSearch, a BM25 variant) and the leakage detector |
| known-good and known-bad scripted answers | `seeds/coding/_selftest/` | harness self-test: 1.0 and 0.3 on the QC item, verified today |
| retry-until-checker-passes, escalation ladder | not yet | AAM; T2's deterministic checker makes retry cheap, so retries must be counted in cost |
| human expert on a sample | not yet | ABC R.12 |

### 6.6 Metrics by tier and plots

Per family and per tier: score with CI, cost with CI, and a Pareto scatter
(cost ascending, score descending sweep, frontier highlighted) with hatched
markers for unpinned or unverified rows and hollow markers for rows without a
cost. The existing `site/app.js` `computeParetoFront` is reused; a
per-family panel and error bars are to add.

## 7. Repo skeleton and the end-to-end path

```
DESIGN.md, OPEN_QUESTIONS.md                      this memo and the decisions needed
docs/rca/{00_frugalmind_inventory,ABC_AUDIT,AUTHORING}.md, docs/rca/prior_art/*.md
src/frugalmind_suites/rca/
  schema/golden_record.schema.json   validate.py   checkers.py   cost.py
  oracles/clock.py                   solvers.py    baselines.py
  inspect_tasks.py                   run.py        pricing/prices.yaml
  seeds/{coding,litreview,sensor}/*.yaml           seeds/coding/_selftest/{good,bad}/
  data/public/*.mseed, *.channels.txt, cassettes/README.md
  data/external/                     gitignored; scripts/rca_fetch_external.py
scripts/rca_fetch_external.py
tests/test_rca_records.py, tests/test_rca_e2e.py
```

End-to-end, verified today on this machine (host sandbox, scratch venv with
inspect_ai 0.3.263 and obspy 1.5.1, no credentials):

```bash
python -m frugalmind_suites.rca.validate
python -m frugalmind_suites.rca.run --ids rca-coding-qc-continuity-001 \
  --solver scripted:src/frugalmind_suites/rca/seeds/coding/_selftest/good \
  --model mockllm/model --epochs 3 --out results/rca
```

produces `results/rca/<run_id>/{summary.json,samples.jsonl,inspect/*.json}`
with score 1.0 in each of 3 epochs, `model_unpinned: true` (mockllm is not a
card), cost null, and the "includes templates" warning. The known-bad answer
scores 0.3 and do-nothing scores 0.0. A real model is one flag away:
`--model anthropic/claude-haiku-4-5-20251001 --allow-unverified-prices`.

## 8. What to do next, in order

1. Marine answers OPEN_QUESTIONS.md Q1 to Q8 (naming, the two unread board
   items, corpus source of truth, licences, prices, T1 tolerance and
   reference, GEPA split).
2. Co-authors replace the 16 templates with verified records (AUTHORING.md),
   starting with the QC control and the two download items.
3. Harness: `fdsn_get_stations` and `ooi_m2m_get` tools; the replay proxy;
   interval F1 for the resync item; judge-span cost exclusion; local-model
   digest pin; Harbor task-dir exporter; `rca_freeze.py`.
4. Rebuild the paper index with dates (`rca_build_corpus.py`) and the sensor
   knowledge base.
5. Only then: first live runs on the validation split with 5 epochs, the ABC
   audit re-run, and the first Pareto plot.
