# Agentic Benchmark Checklist audit of Repère-RCA

Checklist: Zhu et al., "Establishing best practices for building rigorous
agentic benchmarks", arXiv:2507.02825 v5 (43 items: 10 task validity, 20
outcome validity, 13 reporting). Item text paraphrased from the paper; the
full extraction with evidence notes is in `docs/rca/prior_art/papers_aam_abc_gepa.md` §2.
Scoring follows the paper: one point per satisfied applicable item, averaged
per part; items tied to an evaluation method the suite does not use are
not applicable.

Audit date 2026-09-14, state: 16 template records, no verified record, no
live run. Status vocabulary: **pass** (in place and exercised today),
**partial** (designed and partly implemented), **fail** (not in place),
**n/a** (method not used).

## Task validity (10 items)

| id | requirement | status | evidence / what is missing |
|---|---|---|---|
| T.1 | tool versions specified | partial | sandbox image pins python 3.10, numpy 1.26.4, obspy 1.4.1 (`docker/sandbox.Dockerfile`); `sandbox.image_digest` is TODO on every record; host backend is unpinned |
| T.2 | required APIs consistently accessible | fail | no pre-flight health check of EarthScope, OOI M2M or PI portals; availability service returned "Service Unavailable" during this session, which shows why one is needed |
| T.3 | evaluation terminates or handles API outages | partial | void taxonomy implemented in `inspect_tasks.py` (voids excluded from aggregates, counted); network-related voids exist for policy reasons, not yet for live outages |
| T.4 | residual state cleared between runs | partial | repere sandbox creates a fresh tmpdir per snippet; input files are staged per run; no shared HTTP cache; not yet tested for cross-sample leakage with the Docker backend |
| T.5 | agent isolated from ground truth | partial | `public_view` strips reference outputs, citations, checker `expected` and oracle args from sample metadata (tested); T1 public reference (chronfix file) is downloadable in principle, mitigated by `network: none` and by keeping test items on uncovered windows (Q7) |
| T.6 | setup does not change over time | partial | design chooses replay as the scored default (DESIGN.md §5.3) and voids `replay` records until the proxy exists; fixtures and corpora are hash-pinned; live track labelled |
| T.7 | ground truth verified for correctness | fail | every record is a template; `status: verified` requires a second person and `provenance.verification` (R10) but none exists yet |
| T.8 | each task verified solvable | partial | the QC control has a known-good self-test that scores 1.0 (verified today); T1 offset item's self-test solution is a TODO; 14 other records unverified |
| T.9 | oracle solver included | partial | T1 oracle (`oracles/clock.py`) implemented and checked (offset at 2023-03-15T12 = -2.27 s, 32 triggers); T2 self-test answers for one record; none for T3/T4 |
| T.10 | no exploitable shortcuts | partial | checker modules restricted to `repere_suites.rca`; BM25-only baseline designed as the leakage detector (not yet run); no cheating-agent CI run yet |

Part score: 0 pass of 10 applicable (all partial or fail).

## Outcome validity (20 items)

| id | requirement | status | evidence / what is missing |
|---|---|---|---|
| O.a.1 | semantic equivalents accepted (matching) | partial | `exact_match` normalises whitespace and case and accepts a list of forms (channel-code item); no alias table for instrument ids or units yet |
| O.a.2 | redundant words tolerated | pass | substring match on the normalised completion |
| O.b.1 | negation handled | fail | "not BHZ" would pass the substring check; needs a negation guard |
| O.b.2 | robust to listing all answers | partial | nDCG penalises long lists implicitly; `citation_support` has a precision half; `exact_match` does not penalise a list of every channel code |
| O.b.3 | ground truth complex enough to prevent guessing | partial | T1 continuous values with tolerance, T2 record counts; sensor items with 2-token answers are guessable and need chance-level reporting |
| O.c.1 | judge accuracy, self-consistency, human agreement documented | fail by design | T4 scorer refuses to score until `human_ratings_ref`, `calibration_set_ref` and agreement exist (R06); nothing measured yet |
| O.c.2 | judge resists adversarial inputs | fail | no adversarial probe set |
| O.d.1 | test cases verified (human) | partial | checkers reviewed by no second person; known-good and known-bad self-tests exist for one record |
| O.d.2 | test quality measured objectively | fail | no coverage or mutation metrics over the checkers |
| O.e.1 | edge cases addressed (fuzz) | n/a today | no fuzz-tested item; when 1b positives exist, gaps, overlaps, NaN and time-zone edges belong here |
| O.e.2 | input variation coverage | n/a today | |
| O.e.3 | sensitive inputs | n/a today | |
| O.f.1 | E2E tests exercise all code parts | partial | fetch, QC, detect covered by seeds; parse and calibrate not yet |
| O.f.2 | no flaky results | partial | fixed fixtures, float tolerances; sandbox timeouts are wall-clock (a slow host can turn a pass into a timeout); replay not implemented |
| O.g.1 | all success states enumerated (state matching) | partial | the M2M/FDSN item accepts two routes but the checker cannot yet express per-route expectations (TODO in record) |
| O.g.2 | irrelevant state checked | fail | input files are excluded from artifacts but no check that the agent did not alter them |
| O.g.3 | trivial modifications cannot pass | pass | do-nothing scores 0.0 on every scorable item (verified today); `all_or_nothing` on the negative-case control |
| O.h.1 | answer format specified in task | pass | prompts state units, sign convention, keys and ISO-8601 |
| O.h.2 | random guessing minimised | partial | see O.b.3 |
| O.i.1 | quality metrics resist reward hacking | fail | no reward-hacking judge over trajectories; retry-until-pass not yet counted in cost |

Part score: 3 pass of 17 applicable.

## Benchmark reporting (13 items)

| id | requirement | status | evidence / what is missing |
|---|---|---|---|
| R.1 | open-sourced | partial | repere is a private repository; the design plans a public release with the validation split |
| R.2 | open evaluation harness | partial | one-command run exists (`run.py`); private today |
| R.3 | contamination measures | partial | test split private (R08), canary field, cutoff dates, corpus snapshots; no canary values assigned yet |
| R.4 | plan to update challenges | partial | DESIGN.md §5.4 binds a leaderboard to a suite version and names re-recording; no written refresh schedule |
| R.5 | capability-to-construct statement | pass | DESIGN.md §2 and §3 state per tier what is measured and how |
| R.6 | evaluation subject stated | pass | agent systems (model plus scaffold plus prompt) at a stated cost; `label` field on runs |
| R.7 | flaw prevention and correction steps | partial | this audit; validator rules; void taxonomy |
| R.8 | qualitative discussion of unavoidable flaws | pass | DESIGN.md §3.1c (T1 reference caveat), §3.2 (year-only dates), §5.3 (drift) |
| R.9 | quantitative analysis of unavoidable flaws | fail | no drift report, no judge-noise bound, no annotator disagreement rate yet |
| R.10 | statistical significance (CIs) | partial | bootstrap CI over records and per-record sd in `run.py`; needs 5 epochs and more than one record to be meaningful |
| R.11 | interpretation guidance | partial | DESIGN.md §3.1 void-vs-fail and §6.3 unpinned flags; per-tier notes to write |
| R.12 | non-AI (human) baselines | fail | none |
| R.13 | trivial agents reported | partial | do-nothing and BM25-only implemented; do-nothing run today on all 16 seeds; not yet on a leaderboard |

Part score: 3 pass of 13.

## Summary

| Part | pass | partial | fail | n/a | score (pass / applicable) |
|---|---|---|---|---|---|
| Task validity | 0 | 8 | 2 | 0 | 0.00 |
| Outcome validity | 3 | 8 | 6 | 3 | 0.18 |
| Reporting | 3 | 7 | 3 | 0 | 0.23 |

The suite fails the checklist today, as any suite made of templates must.
The items that block a first reported number, in order: T.7 and T.8
(verified records with self-tests), T.6 (replay proxy), T.2 and T.3 (health
checks and outage voids on the live track), O.c.1 (judge calibration before
any T4 number), R.12 and R.13 (baselines on the board), R.9 (drift and
agreement numbers). Re-run this audit at every suite version and store the
table in the paper artifact (DESIGN.md §5.4).
