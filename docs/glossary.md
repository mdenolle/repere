# Glossary

Every metric, tier and field name Repère uses, with the file that owns it.

This file exists because the vocabulary outgrew the documentation. Before it, the
word "tier" carried five unrelated meanings, "frugality" carried two, and "Family 1"
meant literature in one half of the repository and coding in the other. Where a term
is already defined in the paper or a design document, this glossary quotes that
definition rather than restating it, so the two cannot drift.

**If you add a metric, a scorer name or a row field, add it here in the same commit.**

---

## 1. Tiers, bands and levels

Five independent vocabularies used to share the word "tier". They no longer do.

| Vocabulary | Prefix | Answers | Values | Owner |
|---|---|---|---|---|
| Scorability tier | `T` | how strong a scorer can this task support? | T0–T4 | [`docs/dataset_submission.md`](dataset_submission.md) §4 |
| Verification tier | `V` | how was the truth established? | V1–V4 | [`rca/schema/golden_record.schema.json`](../src/repere_suites/rca/schema/golden_record.schema.json) |
| Difficulty level | `L` | how much is withheld from the agent? | L0–L4 | [`docs/ecosystem/05_eval_design.md`](ecosystem/05_eval_design.md) |
| Model size band | — | how big is the model? | nano…cloud | [`config/models.yaml`](../config/models.yaml) |
| Paper difficulty | — | how much of the paper does the model see? | easy, medium, hard | [`paper_workflow/papers.yaml`](../src/repere_suites/paper_workflow/papers.yaml) |

### 1.1 Scorability tiers (T0–T4)

A property of the **scorer**: how verifiable the check is. From
`paper/manuscript.md` Methods:

> **T0**, deterministic matching of an exact or structured value with tolerance;
> **T1**, numerical agreement with a reference array or scalar; **T2**, perceptual
> comparison against a reference artefact; **T3**, agreement of a realised process
> or call graph with a reference trajectory; **T4**, a rubric applied by a model
> judge.

The construction rule: express every task at the strongest tier it admits, and use
T4 only where no lower tier can encode the check.

T4 comes in two kinds, which must be distinguished on any row that uses one:

| Kind | Output | Rubric lives in | Reproducibility |
|---|---|---|---|
| free-text judge | prose, parsed by regex | a prompt file | varies run to run |
| typed judgment | distribution over declared options | level descriptions plus weights in code | to be measured |

### 1.2 Verification tiers (V1–V4)

A property of the **record**: where its truth came from. RCA only. Renamed from
`T1_physics`…`T4_judgment` so the token `T1` has one meaning.

| Tier | Truth comes from | Method | Maps to |
|---|---|---|---|
| `V1_physics` | an independently measured physical quantity with an oracle solver | `oracle_compare` | T1 |
| `V2_execution` | executing the generated code and checking the result | `execution_check` | T0/T1 |
| `V3_reference` | a date-bounded reference corpus with graded relevance | `retrieval_metrics`, `citation_support`, `exact_match` | T0 |
| `V4_judgment` | an expert rubric | `rubric_judge` | T4 |

The mapping is not one-to-one: V2 spans T0 and T1, V3 is entirely T0. Full table in
[`DESIGN.md`](../DESIGN.md) §3.1.

### 1.3 Difficulty levels (L0–L4)

A property of the **task**, orthogonal to both tiers above. L0 is a single tool call
on clean data with a full spec; L4 is an underspecified scientific goal scored by
call-DAG. Scoring stays T0/T1 through L3. Planning vocabulary only; no code reads it.

### 1.4 Model size bands

`nano` <2B, `small` 2–9B, `medium` 9–35B, `big` 35–200B, `cloud` API-served.
Validated by `VALID_SIZE_BANDS` in [`registry.py`](../src/repere/registry.py); filter
with `cards_in_size_band`. Was `tier:` in `config/models.yaml` until the rename.

---

## 2. Scorer names

The `{"name": ..., "config": {...}}` strings a suite row can carry. Each suite's
`make_scorer_from_spec` rebuilds the callable from the spec, which is what lets a
benchmark row be scored by a third party without running our code.

### 2.1 STA/LTA — `sta_lta/scorers.py`

| Name | Computes | Reference needed | Tier |
|---|---|---|---|
| `json_extraction` | fraction of `required_fields` matching gold; ISO times within a per-field second tolerance, strings case-insensitively | gold dict | T0 |
| `code_execution` | four flat 0.25 stages: code extracted, required calls present, sandbox run ok, artifacts pass predicates | config only | T0 |
| `plot_ssim` | SSIM of the produced PNG against a golden PNG | golden PNG | T2 |
| `report` | lexical: 0.4 detection words + 0.3 origin time + 0.3 magnitude, −0.25 per forbidden term. Optional judge fallback returns `max(lexical, judge)` | catalog facts | T0, T4 if the judge runs |
| `zero` | always 0.0, for items whose golden artifact is missing | none | — |

Artifact predicates: `int_ge_1`, `int_eq_0`, `float_gt_0`.

### 2.2 Literature and RAG — `lit_rag/scorers.py`

| Name | Computes | Reference needed | Tier |
|---|---|---|---|
| `retrieval_metrics` | one ranking metric over a parsed ranked id list | gold relevant ids | T0 |
| `term_preservation` | fraction of `required_terms` present, minus `1/len(required)` per forbidden term | config only | T0 |
| `citation_support` | `0.5·validity + 0.5·coverage − 0.25·forbidden`; validity is the fraction of `[S#]` resolving to a provided source | `valid_sources` | T0 |
| `attribution` | `⅓·validity + ⅓·recall + ⅓·coverage − 0.25·forbidden`, with precision and the list of fabricated ids in `.breakdown`; reads DOIs, `[S#]`, and numbered `[n]` against the listed sources | `valid_sources`, `relevant_sources` | T0 |
| `abstention` | 1 for a clean `NO_RELEVANT_PAPERS` on an unanswerable query, 0 for any answer; on an answerable query 0 for declining, else recall of the gold ids | `answerable`, gold ids | T0 |

`citation_support` checks a citation **resolves**, not that the passage supports the
claim. The second question is `jev_grounding` (§2.6).

### 2.3 Numerical regression — `pipeline_regression/scorers.py`

`numerical_regression`: staged weighted sum, code 0.1 / calls 0.1 / runs 0.1 /
accuracy 0.7, against a reference scalar or array. Tier T1.

### 2.4 Synthetic STA/LTA — `synthetic_stalta/scorers.py`

| Name | Computes | Stage weights |
|---|---|---|
| `stalta_code` | model writes a detector, waveform injected into the sandbox, accuracy by `pick_f1` | code 0.1 / runs 0.1 / accuracy 0.8 |
| `detection_picks` | `pick_f1` of parsed onsets, default tolerance 1.5 s | — |

### 2.5 Orchestration — `orchestration/scorers.py`

| Name | Computes |
|---|---|
| `trajectory_dag` | node F1 0.4 / edge F1 0.4 / frugality 0.2 against a reference DAG. A malformed, cyclic or dangling-dependency plan scores 0 outright |
| `trajectory_policy` | fraction of conditional invariant rules satisfied over a recorded trace |

Policy rule kinds: `precondition`, `guard`, `branch`, `recovery`, `termination`.

### 2.6 Typed judgment — `repere/jev_scorers.py`

| Name | Computes | Reference needed |
|---|---|---|
| `jev_grounding` | fraction of cited claims the cited passage supports. Above the confidence floor a supported claim scores 1.0; below it, the probability mass on `supports`. A citation to a source the item never provided scores 0 by dict lookup, with no request sent | the passages themselves |
| `jev_claimed_vs_actual` | honesty 0.6 / disclosure 0.2 / method 0.2. Honesty is whether the prose claim matches `actual_success`, which the sandbox measured | `actual_success` |

Both are off unless a client is injected; neither can reach the network from CI.

### 2.7 dv/v — `dvv/scorers.py`

`dvv_recovery` and `dvv_series_regression` are implemented in the pinned external
`codameter` package, not here. `dvv_series_regression` is null-anchored, so
predicting no change scores about 0.

---

## 3. Sub-metrics

Named inside a scorer's `config`, not selectable on their own.

| Name | Definition | Used by |
|---|---|---|
| `recall_at_k` | relevant documents in the top k, over all relevant | `retrieval_metrics` |
| `precision_at_k` | relevant documents in the top k, over k | `retrieval_metrics` |
| `mrr` | reciprocal rank of the first relevant document | `retrieval_metrics` |
| `ndcg_at_k` | binary-gain DCG over ideal DCG, both truncated at k | `retrieval_metrics` (default, k=10) |
| `pick_f1` | F1 of greedily time-matched picks within a tolerance; empty against empty is 1.0 | `detection_picks`, `stalta_code`, `numerical_regression` |
| `allclose` | fraction of elements within `atol + rtol·|gold|` | `numerical_regression` |
| `pearson` | `max(0, r)`; a shape metric for cross-correlation functions | `numerical_regression` |
| `rmse` | `max(0, 1 − rmse/rmse_scale)` | `numerical_regression` |

`pick_f1` is defined twice, in `pipeline_regression/scorers.py` and
`synthetic_stalta/scorers.py`, deliberately and with a comment in each.

---

## 4. Agent metrics — `repere/agents/metrics.py`

The second axis. Task correctness says whether the answer was right; these say
whether the model could drive the harness at all. A model scoring 0 because it never
emitted a valid submit is failing differently from one that submitted a wrong answer,
and collapsing them hides which.

| Name | Definition |
|---|---|
| `n_tool_calls` | total tool invocations; a cost and effort proxy |
| `n_tool_errors` | tool results returning an error, plus parse errors on calls |
| `distinct_tools` | sorted list of tool names used |
| `submitted` | whether `record_submit` was ever called |
| `converged` | submitted, and no error on the last tool call |

---

## 5. RCA record fields

| Field | Meaning |
|---|---|
| `shape` | `A_text` (the answer is prose) or `B_tool` (something must execute) |
| `status` | `template` → `draft` → `verified` → `frozen` → `retired`. Only `verified` and beyond may produce a ranked number |
| `void` | the harness could not score, for a reason that is not the agent's fault. Excluded from aggregates and counted separately. **A zero without `void` is a real failure**; a void is not a zero |
| `canary` | a unique searchable GUID embedded in held-out prompts, so training-set scraping is detectable |
| `cutoff_date` | the date past which a retrieval tool must not return content for this item |
| `scoring.metrics` | the metrics this record's method actually produces. Validated by **R16** against `_METHOD_METRICS`; before R16 nothing read this field |

### 5.1 Holdout construction

How an item avoids being answerable by looking it up in the corpus it was drawn from.

| Value | Rule |
|---|---|
| `catalog_perturbed` | the gold differs from the catalog by a verified fact |
| `catalog_excluded` | the referenced entry is removed from the snapshot the agent sees |
| `cross_source_join` | the answer needs a source outside the corpus |
| `temporal_after_index` | the content postdates the snapshot; the correct answer is abstention |
| `held_out_site` | a whole site is excluded; reserved for the test split |
| `paraphrase_only` | the prompt paraphrases a catalog field. Validation split only, never test (R08) |
| `none` | not catalog-derived |

Note the distinction from prompt-robustness paraphrases: those are a measurement over
an existing item, generated at run time and never written to a record, so R08 does
not apply to them.

---

## 6. Evaluation-design terms

**Quality floor.** From `paper/manuscript.md` Methods:

> the score below which an output is not scientifically usable. The floor is a
> property of the task and the discipline, set by what a reviewer would accept, and
> not of the model.

Implemented as `quality_floors: dict[TaskKind, float]` in
[`router.py`](../src/repere/router.py).

**Frugality.** Two senses, both legitimate, never interchangeable:

1. *The thesis.* The interesting winner is the cheapest system that still clears the
   quality floor. This is what the leaderboard's cost axis measures.
2. *A scorer stage.* A 0.2-weight term inside `trajectory_dag` penalising an
   orchestrator that fans out more sub-agent calls than the reference plan needs.

Write "the frugality stage" when you mean the second.

**Negative-case discipline.** Every evaluation must contain instances whose correct
answer is explicitly nothing. Three of the eleven detection cases in E1 are
noise-only, and reporting an event in them is penalised exactly as missing a real
one. This makes confident fabrication a scored outcome rather than an invisible one.

**Parametric truth set.** A truth set generated from parameters rather than
hand-labelled, so the reference is known exactly and the split can be regenerated
from a secret seed rather than stored.

**Skill.** Versioned, human-authored domain guidance attached to a task: what a senior
colleague would tell a new student before they touched the data. Not a prompt
heuristic. Carries a name, a semantic version and a change history, and every score
records the version that produced it.

**Skill lift.** `score_full − score_none`: the change in deterministic score
attributable to loading the skill. It can be negative, and on STA/LTA code generation
it is, for three of the five models on the July board.

**Stage weights.** Several scorers decompose a score into stages. The splits differ on
purpose, and the difference is the claim each scorer makes about what matters:

| Scorer | Split |
|---|---|
| `numerical_regression` | code 0.1 / calls 0.1 / runs 0.1 / accuracy 0.7 |
| `stalta_code` | code 0.1 / runs 0.1 / accuracy 0.8 |
| RCA `staged_score` | code 0.1 / runs 0.2 / correct 0.7 |
| `trajectory_dag` | nodes 0.4 / edges 0.4 / frugality 0.2 |
| `code_execution` | four flat 0.25 stages |

Each scorer documents what its stages *measure*; none documents why its weights are
the numbers they are. RCA's 0.2 on `runs` against everyone else's 0.1 is the
divergence worth settling first: either an OOI download that executes at all has
cleared most of the difficulty, which would justify it, or the number is an accident
nobody has revisited. P3.5 (per-suite `RUBRIC.md`) is where the answers belong; record
them here too when they exist.

---

## 7. Leaderboard fields

Row schema in [`leaderboard.py`](../src/repere/leaderboard.py).

| Field | Meaning |
|---|---|
| `agent_condition` | which scaffolding produced the row, e.g. `generic-coding-agent` or `stalta-detection+skill-v0.3`. See [`leaderboard_conditions.md`](leaderboard_conditions.md) |
| `openness` | `open-source-open-weight`, `open-source-closed-weight`, `closed-source-api`, `closed-source-ui`, `unknown` |
| `toolset` | `standard`, `custom-interface`, `custom`, `unknown` |
| `cost_usd` | realised dollar cost of the agent run, from token usage. Local models are 0 marginal dollars, which is true of dollars and false of cost |
| `scoring_cost_usd` | what it cost to *score* the run. Kept separate: folding it into `cost_usd` would corrupt the axis the project exists to measure |
| `skill_name`, `skill_version` | which versioned domain guidance was loaded for this row, or null for the no-skill arm. Every score records the exact version that produced it |

### 7.1 Quality, as a distribution (v0.2)

| Field | Meaning |
|---|---|
| `score_mean` | mean deterministic score over `n_epochs` repeats, in [0, 1] |
| `score_ci95` | half-width of a 95% Student-t interval **over repeat runs**. `null` below two epochs, never `0.0` — a renderer must be able to tell "not measured" from "measured, no variance" |
| `score_runs` | the raw per-epoch scores, so a reader can recompute any statistic |
| `n_epochs` | how many times this configuration was run. 1 means a point estimate |

### 7.2 Cost, on every axis we can measure

| Field | Meaning |
|---|---|
| `in_tokens`, `out_tokens`, `total_tokens` | the provider-independent cost proxy. Prices move under a published benchmark; tokens let a reader re-price the board (issue #41) |
| `latency_s_mean`, `latency_s_ci95` | wall clock per run. The cost a $0 model still charges (issue #44) |
| `n_tool_calls`, `n_agent_steps` | fan-out, which is where orchestration cost explodes rather than tokens (issue #42) |

### 7.3 Provenance and frontier

| Field | Meaning |
|---|---|
| `phase` | `baseline`, `fault`, `structural`, or `prompt`. A perturbed run is not comparable to a clean one, so the provenance travels with the number and only `baseline` rows compete for a frontier |
| `perturbation_seed`, `fault_rate` | what was done to the environment, so a perturbed row is reproducible |
| `on_frontier_cost`, `on_frontier_tokens` | whether the row is a vertex of its suite's convex hull on that axis. **Per suite**: a 1.00 on dv/v and a 1.00 on literature retrieval are not the same achievement. The two axes disagree, which is why both are reported |

### 7.4 Retired in v0.2

| Field | Why it went |
|---|---|
| `score` | replaced by `score_mean` + its interval. A bare number from one run is not a measurement of a stochastic system |
| `quality_percent` | `score × 100` carried no information the score did not, and invited reading a percentage without its interval |
| `efficiency_score` | score per dollar. Unbounded, `null` for every zero-cost row, defined nowhere, read by nothing. The frontier flags answer the question it was reaching for |

---

## 8. Reliability metrics

Implemented in [`reliability.py`](../src/repere/reliability.py); carried on a row
in the nullable `reliability` block. Provenance for every definition is
[`ecosystem/hal_adoption.md`](ecosystem/hal_adoption.md).

Three conventions hold across all of them:

- **Higher is better**, including for metrics the source literature reports as
  errors. The two exceptions are named `_rate` and are called out below.
- **`None` means not measured**, never zero. Reliability needs repeats, and most
  of these need a whole extra run phase.
- **Reliability is not capability.** Every one of these normalises by the
  agent's own baseline or by its own success rate, so a weak model that fails
  identically every time scores high on consistency. Read them beside
  `score_mean`, never instead of it.

### 8.1 Consistency — does it agree with itself?

| Row field | Function | Definition | Needs |
|---|---|---|---|
| `consistency_scope` | — | `"record"` (per item, then averaged: the statistic as defined) or `"arm"` (whether the whole suite mean cleared the floor on each run). The coarse form is all that is recoverable when a runner kept only per-run means; it is labelled rather than passed off as the finer one | — |
| `consistency_outcome` | `outcome_consistency`, per record `record_consistency` | `(2p̂−1)²` per record, averaged, where `p̂` is the fraction of epochs that pass. 1.0 when every epoch agrees, 0.0 at an even split | K ≥ 2 epochs |
| `consistency_resource` | `resource_consistency` | `exp(−mean CV)` over cost, latency, tokens and tool calls. A local model billing $0 every run contributes CV 0, which is stability, not an undefined ratio | K ≥ 2 epochs |
| `consistency_trajectory_dist` | `trajectory_consistency_dist` | `1 − mean pairwise Jensen-Shannon divergence` over tool-name distributions. Ignores order | K ≥ 2 traces |
| `consistency_trajectory_seq` | `trajectory_consistency_seq` | `1 − mean pairwise normalised Levenshtein` over tool-call sequences. Sees order | K ≥ 2 traces |

Report both trajectory metrics: an agent can be stable in what it reaches for
and unstable in how it sequences it. `consistency_all_pass`, which the RCA
runner already had, is a cliff — one failed epoch in five reads the same as five
— so it stays, but `consistency_outcome` is what grades the disagreement.

### 8.2 Robustness — does it survive a degraded environment?

All three are computed by `robustness_ratio` as `min(Acc_perturbed / Acc_baseline, 1)`, clamped so that scoring
better under perturbation reads as "fully robust" rather than as a bonus.
`None` when the baseline is zero: an agent that fails the clean task has no
robustness to measure.

| Metric | Perturbation | Geoscience instances |
|---|---|---|
| `robust_fault` | injected tool failures at `fault_rate` | FDSN 503 and timeout, M2M partial return, truncated miniSEED, empty stream |
| `robust_structural` | the interface reshaped without changing meaning | epoch vs ISO-8601 vs slashed time, `""` vs `--` for an empty location code, a dotted SEED id vs its four named components, `starttime` vs `start_time`, key order, `40` vs `40.0` |
| `robust_prompt` | J semantically equivalent paraphrases | generated per item at run time, never written to a record — see §5.1 on why this is not `paraphrase_only` |

Meaning preservation is the hard constraint, and geophysics decides it. An
empty location code has three spellings in the wild (`""`, `--`, two spaces)
and clients disagree about which to send, so respelling it tests robustness.
Renaming `BHZ` to `HHZ` does **not**: those are different channels at
different sample rates (40 Hz and 200 Hz on the COSZO stations), so an agent
that answered differently afterwards would be correct to. If a domain expert
would change their answer, it is a different task, not a perturbation.
`tests/test_perturbations.py` asserts that no transform in the catalogue
touches a channel code.

### 8.3 Predictability — does its stated confidence mean anything?

All three require the agent to emit a self-reported confidence, which the
harness does not yet ask for. Until that protocol exists these are `None` on
every row.

| Metric | Definition |
|---|---|
| `calibration_ece` | `1 − ECE`: 1.0 when stated confidence matches observed accuracy in every bin |
| `brier` | `1 − mean (confidence − outcome)²`. A proper scoring rule: rewards being calibrated *and* decisive |
| `auroc` | probability a successful task was given higher confidence than a failed one. Ties count as half |

Report calibration and AUROC together. A model that says 0.5 on everything and
is right half the time is perfectly calibrated and completely uninformative;
only AUROC catches it, at exactly 0.5.

### 8.4 Integrity — the scientific replacement for a generic safety axis

The published safety dimension this parallels is PII, destructive operations and
policy circumvention. The scientific analogue is fabricating a citation,
overclaiming a result, and crossing a data licence or embargo. Following the
same structural rule as the source work, integrity is reported **separately and
never averaged into a headline**, so a tail risk cannot be masked by a good mean.

All five are proportions over per-item booleans the scorers already emit, so
they share one implementation, `proportion`, and differ only in which flag is
counted.

| Metric | Counts | Orientation | Source |
|---|---|---|---|
| `integrity_grounding` | cited claims the cited passage actually supports | 1.0 good | `jev_grounding` |
| `integrity_abstention` | items where the agent correctly declined | 1.0 good | typed abstention check |
| `integrity_cutoff_compliance` | runs with no retrieval past the item's `cutoff_date` | 1.0 good | aggregate of the cutoff tests |
| `integrity_citation_fabrication_rate` | `[S#]` citations resolving to no provided source | **0.0 good** | `citation_support` |
| `integrity_overclaim_rate` | reports claiming success on a run the checker failed | **0.0 good** | `jev_claimed_vs_actual` |

The two `_rate` metrics are the exceptions to the higher-is-better convention.
The site renders them on an inverted scale and this table is the reason.

### 8.5 Intervals — two of them, over two different populations

| Function | Population | Returns |
|---|---|---|
| `student_t_ci` | repeat runs of one configuration | half-width of a 95% interval |
| `bootstrap_ci` | records within a suite | `(lo, hi)` percentile bounds, seeded |

These answer different questions and are not comparable. `score_ci95` on a row
is the first; `bootstrap_ci95_over_records` in an RCA summary is the second.

---

## 9. Families

Two numbering schemes exist and **they disagree**, so prefer the names.

| Repère family | RCA agent role |
|---|---|
| 1 · literature, RAG, multimodal | `coding` |
| 2 · coding agents | `litreview` |
| 3 · orchestration | `sensor` |

Repère's Family 1 is literature; RCA's family 1 is coding. Say "the litreview agent"
or "Family 1 (literature)", never a bare "family 1".
