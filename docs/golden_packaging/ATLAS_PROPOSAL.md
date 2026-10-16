# Proposal: packaging the RCA Atlas baseline evals as Repère golden sets

Status: proposal, not implemented. Nothing in this file has been run against
Repère's scorers.

Source: the 2026-10-08 baseline catalog,
`coszo-hub/RCA-Atlas` branch `rca-atlas-eval-suite`,
`src/atlas_eval/results/2026-10-08-baseline/catalog.html`. Counts below come
from the JSON embedded in that page (715 cases, 11 suites), read on 2026-10-15.
Method write-up cited by the page:
`src/atlas_eval/EVALUATION_METHOD.md` at `e8d828d`. I have not read it, nor the
`datasets/*.jsonl` files the page links to.

Read [`README.md`](README.md) first for the row format and the A/B decision rule.

## Verdict

Seven of the eleven Atlas suites are synthetic with a seeded generator
(gaps, timing, dvv, pressure, agent, agent_llm, and the windowing half of
quakes). They are Mode A: package the generator and a secret, store nothing.
Four suites are human-written or corpus-bound (routing, quake_questions,
retrieval, answers). They are Mode B and need a real public/hidden split that
does not exist yet.

One action is needed before any of it is packaged: the published catalog
exposes the held-out data (next section).

## Problem 1: the catalog page publishes the answers

`catalog.html` embeds every case with its full record. In that JSON:

| Suite | Evidence the page carries gold | Rows |
|---|---|---|
| routing | `split: "test"` rows with `task` (the gold label) | 73 test, 83 dev |
| retrieval | `gold.reference_answer`, `required_chunk_ids` | 60 |
| answers | `gold.reference_answer`, `required_chunk_ids`, `required_citations` | 60 of 72 |
| quake_questions | `expected` date range and magnitude | 26 |

The page loads without credentials through raw.githack, which serves public
GitHub content. I did not check the repository's visibility settings. If the
page is public, then under `docs/holdout_policy.md` the routing test half is
already burned for ranked use: its labels and questions are readable. The same
policy treats the human-written suites as having no hidden partition at all.

Fix, in order:

1. Decide per suite which rows are the held-out partition (section "Splits").
2. Re-cut the held-out rows from questions that have never been in the repo, its
   history, or a published page. Do not move the existing test rows; they are
   spent.
3. Make the catalog generator omit `gold`, `expected` and `reference_answer`
   for test-split rows. Aggregates and per-case pass/fail stay.
4. Note the retirement date of the old split in the changelog so a published
   number is attributable to one split.

## Task-type mapping

`task_kind` is a `repere.TaskKind` value. `Scorer` says whether it exists today
(file checked, not run) or must be written and registered in a
`make_scorer_from_spec`.

| Atlas suite | n | task_kind | Scorer | Tier | Mode | Gold |
|---|---|---|---|---|---|---|
| routing | 156 | `orchestration` | `exact_match` on `task` (**register**; exists only as an RCA method) | T0 | B | label from 15-class set |
| quake_questions | 26 | `extraction` | `json_extraction` (exists, `sta_lta/scorers.py`) | T0 | A for templated rows, B for paraphrases | `{start, end, min_mag}`; `now_utc` goes in the prompt |
| retrieval | 60 | `retrieval` | `retrieval_metrics` (exists, `lit_rag`) | T0 | B | `required_chunk_ids`, plus `corpus_snapshot` |
| answers | 72 | `grounded_qa` | `citation_support` (exists, `lit_rag`) as primary; `rubric_judge` as secondary | T0, T4 | B | `reference_answer`, `required_terms`, `required_chunk_ids` |
| quakes | 35 | `numerical_regression` | exact integer or histogram match (**new**, or `numerical_regression` with tolerance 0) | T1 | A for windows, public fixture | computed by an oracle at scoring time |
| gaps | 120 | `extraction` | fault-set F1 with interval overlap (**new**: `fault_f1`) | T0 | A | list of `{kind, start, length}` |
| timing | 60 | `numerical_regression` | per-hour error against generative truth, pass if within 1 sample (**new**, or RCA `oracle_compare`) | T1 | A | `jump_s`, `jump_hour`, `drift_s_per_day`, `kind` |
| dvv | 72 | `numerical_regression` | `numerical_regression` (exists, `pipeline_regression`) | T1 | A | `dvv` (fractional) |
| pressure | 72 | `numerical_regression` | `numerical_regression` on model parameters | T1 | A | calibration offsets, `rate_kpa_per_yr`, settling `amp` and `tau` |
| agent | 21 | `orchestration` | `trajectory_dag` (exists, `orchestration`) plus answer check | T3 | A | expected answer and required tool |
| agent_llm | 21 | `orchestration` | same dataset as `agent` | T3 | A | same |

Notes on the table:

- **agent and agent_llm are one dataset.** The two differ in who solves the
  tasks (scripted oracle vs `claude:haiku`), which is run configuration, not
  data. Package once, as `atlas/agent`, and record the solver on the leaderboard
  row. The oracle run is the ceiling check, not a benchmark result.
- **retrieval and answers share questions.** Ids match (`instrument-001` is in
  both). Ship two suites with the same `prompt` and `gold` and different
  `scorer_spec`, so a change to a question bumps both versions together.
- **dvv already has a Repère suite** (`codameter`, Mode A, secret
  `CODAMETER_GOLDEN_SECRET`; `docs/dvv_suite_v0.md`). Reuse its generator and
  seed policy. Do not hold a second hidden corpus for the same quantity.
- **Existing scorer names were read from `make_scorer_from_spec` source, not
  run.** Confirm each round-trips before the first export.

## Per-suite preparation

### Mode A suites (gaps, timing, pressure, dvv, agent, quakes windows)

Atlas already seeds each case (`gaps-001` seed 1000, `timing-001` seed 2000,
`dvv-001` seed 3000, `pressure-001` seed 4000, `agent-diagnose-1` seed 6000). Keep that
generator as the public validation set and add a second one:

1. Write `generate(secret, version) -> cases` that reproduces today's
   validation cases exactly when given the public seed, and a distinct draw
   when given the secret. Today's seeds are in the catalog; the secret must not
   be derivable from them.
2. Split the generator output into an **observable** part (the series file,
   the station records, the question text) and a **truth** part (the injected
   faults, `dvv`, offsets). The model gets only the first. In the catalog the
   gaps case record carries `case.faults` next to the series parameters;
   make sure the sandbox view contains the series and not that list.
3. Publish `sha256(cases.json)` for the hidden draw as the commitment. Keep the
   contents in the runner temp dir for the life of the job.
4. Add the scorer, register it, and add a round-trip test.

Per suite:

- **gaps.** Seven fault kinds appear (zero_fill 46, duplicate 41, nan_fill 40,
  gap 37, spike 37, backstep 36, flatline 25 injections). 20 of the 120 cases
  inject no fault, so clean series are already covered; keep that share in the
  hidden draw. Score each case by set F1 over kinds and by interval overlap of
  start and length. The one failing case is worth reading before freezing the
  gold.
- **timing.** 15 cases each of `none`, `jump`, `drift`, `jump+drift`, over five
  SNR levels (0.08 to 0.35). Pass is "diagnosis right, jump found, at least 95 %
  of estimated hours within one sample". See the abstention question below.
- **pressure.** Tasks `a0a`, `scpr`, `drift`, 24 each. The headline excludes
  the uplift-confound cases; make that a `metadata.category` so the exclusion is
  a slice, not a silent filter.
- **dvv.** 72 cases, three methods (stretching, MWCS, DTW) scored per case.
  One row per case with the per-method pass rates as separate metrics, or
  three rows per case. The first keeps the row count equal to Atlas's n.
- **quakes.** The fixture catalog is real data, so hold the fixture public and
  pinned by sha256 (RCA rule R13). Generate the query windows from the secret.
  Gold is the count or histogram computed from the fixture at scoring time,
  never typed into a row. Cross-implementation agreement (the catalog tracks
  three: `atlas_tasks`, `axial_agent_tools`, `worker_js`) is a test of the
  oracle, not part of the gold.

### Mode B suites (routing, quake_questions, retrieval, answers)

These need a human to write and a second human to verify.

- **Splits.** Routing has 15 task types at 10 to 12 questions each. A
  held-out half is 3 to 6 per class, so per-class recall is nearly
  uninformative (95 % CI on 4 cases is wide). Report macro-F1 and accuracy only,
  and say so in the dataset card.
- **Verification state.** In the 120 retrieval and answers rows, 30
  (15 questions) carry `review_status: requires_human_review` and 90 carry
  `corpus_verified`. Package the 15 as `draft`, not verified, and exclude them
  from any ranked number until a second named person checks the gold against
  the corpus. The RCA lifecycle in `docs/rca/AUTHORING.md` is the model.
- **Corpus pin.** Retrieval gold is chunk ids. Re-chunking the corpus silently
  invalidates it. Put the corpus snapshot id and hash in
  `metadata.corpus_snapshot` and set `cutoff_date` (RCA rule R05).
- **Abstention.** Include questions whose right answer is "the corpus does not
  establish this". The `tool_avoidance` and `tool_selection` categories in
  retrieval (5 cases) are the start of this; extend them.
- **Answers scoring.** The baseline uses an LLM judge (`claude:haiku`) over
  answers from `gemini-2.5-flash` and gets 79 % [66 %, 88 %] with 6 errored
  cases. In Repère terms that is tier T4. Lead with `citation_support`
  (required terms and valid citations), and report the judge score only after
  two humans have rated a calibration set and agreement is published
  (RCA rule R06). The catalog has 5 `n/a` rows: decide whether they are
  excluded or counted as errors before the first export.
- **quake_questions.** Split by construction: templated questions (date
  ranges, magnitudes, relative dates against a given `now_utc`) are Mode A and
  can be drawn from the secret; the paraphrased ones are Mode B.

## Questions only the domain experts can settle

These change the gold, so they belong to the assigned experts on the sheet.

1. **Does abstaining count as a pass?** In timing, 20 of the 24 failures sit at
   SNR 0.08 (12 of 12 fail) or 0.12 (8 of 12 fail). All 18 abstentions
   (`insufficient_snr`) are scored as fails, and only 1 case is flagged
   confidently wrong. At SNR 0.08 the right answer may be "cannot estimate". If
   so the 60 % headline understates the method and the gold needs an
   `abstain` outcome.
2. **Is 1 sample the right tolerance** (0.125 s at 8 Hz) for the real stations,
   or only for the synthetic pair? chronfix reports a picker quantum of 0.125 s
   and typical sigma 0.08 s on field data (see the `rca-coding-timing-offset`
   seed).
3. **Which pressure cases are the uplift confound**, and are they negative
   controls or excluded?
4. **For the 15 `requires_human_review` questions,** who is the second
   verifier?

## Order of work

| Step | Output | Unblocks |
|---|---|---|
| 1 | Catalog generator stops emitting gold for held-out rows; retire the routing test half | any ranked number |
| 2 | Register `exact_match`; write `fault_f1` and the timing scorer | exports for routing, gaps, timing |
| 3 | `generate(secret, version)` for gaps, timing, pressure, agent; reuse codameter for dvv | Mode A hidden draws |
| 4 | Export public `validation` JSONL and `manifest.json` for the seven Mode A suites | a pinned v0.1 |
| 5 | Verify the 15 draft questions; write new held-out routing, quake_questions, retrieval, answers rows into `$REPERE_EVAL_DATA_DIR` | Mode B hidden split |
| 6 | Upload the gated dataset, record the HF SHA, add the leaderboard pin | ranked results |
