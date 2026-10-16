# What Repère takes from HAL, and under what terms

Companion to [`../rca/prior_art/harbor_tbench_hal.md`](../rca/prior_art/harbor_tbench_hal.md),
which is the survey. This is the decision record: every metric adopted, where the
definition came from, what we changed, and why.

Prepared 2026-09-22. Licence facts re-checked the same day against the GitHub API
and the published pages.

## The rule

**Methods and concepts come from the papers and the public documentation pages.
Nothing comes from the HAL source code.**

Every metric below traces to a citable published statement. Where a definition exists
only in their repository, we do not adopt it — we derive our own or leave it out. No
file, function, constant, rubric string or price table is copied, adapted or
paraphrased from `princeton-pli/hal-harness`.

This is not caution for its own sake. The repository carries **no LICENSE file**
(`gh api repos/princeton-pli/hal-harness --jq .license` → `null`, checked
2026-09-22), and it was archived on 2026-07-01 with `CONTRIBUTING.md` stating that no
new results or pull requests are accepted. Absent a licence, the default is all rights
reserved. A benchmark that publishes numbers has to be able to say where every part of
its method came from.

| Source | Terms | What we may do |
|---|---|---|
| HAL paper, arXiv:2510.11977 (ICLR 2026) | arXiv perpetual non-exclusive licence: a distribution grant to arXiv, not a reuse grant to us | Reimplement described methods from the prose; quote briefly with citation; do not reproduce rubric text verbatim |
| Reliability paper, arXiv:2602.16666 | **CC BY 4.0** | Reuse definitions and formulas directly, with attribution |
| hal.cs.princeton.edu and its reliability dashboard | published prose, cited as a web source with an access date | Adopt definitions stated on the page, with citation |
| `princeton-pli/hal-harness` | no licence, archived | **Nothing**, including as a reference while implementing |
| `agent-evals/hal_traces` (HuggingFace) | no licence set | Do not redistribute |

One consequence for our own records: `../rca/prior_art/harbor_tbench_hal.md` line 11
calls their checked-in price dictionary "the one piece of HAL code worth copying."
That judgement predates this rule and is superseded — see §4.

## 1. Adopted, from the reliability paper (CC BY 4.0)

Cited as `rabanser2026reliability`. Reused directly because the licence permits it.

| Our name | Their definition | Changed? |
|---|---|---|
| `outcome_consistency` | agreement of a task's outcome across K repeats | **yes** — see §3 |
| `resource_consistency` | `exp(−mean_r CV_r)` over resource usage across repeats | no; we fix the resource set to cost, latency, tokens, tool calls |
| `trajectory_consistency_dist` | `1 − mean pairwise Jensen-Shannon divergence` over action-type distributions | no |
| `trajectory_consistency_seq` | `1 − mean pairwise normalised Levenshtein` over action sequences | no |
| `robustness_ratio` | `min(Acc_perturbed / Acc_baseline, 1)` | no |
| `calibration_ece` | `1 − Σ_b (n_b/N)·|ȳ_b − c̄_b|` | no |
| `brier` | `1 − mean (c − y)²` | no |
| `auroc` | fraction of (success, failure) pairs the confidence orders correctly | no |

Their settings adopted as defaults: `K = 5` repeats, `p_fault = 0.2`, `J = 5`
paraphrases per prompt.

Their aggregation convention adopted with one change we should be explicit about:
they exclude safety from the overall reliability average so that averaging cannot mask
tail risk, and report it separately as a hard constraint. We keep that principle and
apply it to our integrity axis (§5), which plays the same structural role.

## 2. Adopted, from the HAL paper (reimplemented from the prose)

Cited as `kapoor2026hal`. Ideas and methods, written fresh.

| What | Why it transfers |
|---|---|
| **Cost-controlled evaluation.** Report cost beside accuracy, always. | Already Repère's thesis; HAL is the strongest external statement of it and the closest prior art after AstaBench |
| **Convex-hull frontier including the origin.** The admissible set is the hull, not the staircase, because a randomised mixture of two agents is deployable; the origin belongs because not deploying is always an option. | Our frontier code was deleted (see below) and has to be written; this is the right construction to write |
| **Report the token frontier beside the dollar frontier.** They disagree — in their data an agent on the token frontier in 3 of 8 benchmarks was on the cost frontier in 1 of 8. | Prices move under a published benchmark. Already filed as issue #41 |
| **Single runs without confidence intervals are not enough.** Their own paper records being forced into them. | `paper/manuscript.md` Methods already carries the same TODO |

Not adopted: their six-part log-analysis rubric. The categories are useful, but the
rubric text is theirs and a geoscience version needs different categories anyway
(a shortcut in seismology is reading the answer out of a catalog, not searching the
web for a benchmark solution). If we build one, it is written from scratch.

## 3. The one place two published sources disagree

Outcome consistency has two published definitions.

The **paper** gives a variance ratio, averaged over tasks:

```
C_out = mean_t [ 1 − σ̂_t² / (p̂_t(1−p̂_t) + ε) ]
```

This is degenerate for Bernoulli outcomes. The sample variance of K binary draws is
`σ̂² = (K/(K−1))·p̂(1−p̂)`, so the ratio is the constant `K/(K−1)` wherever `p̂` is
neither 0 nor 1, and the expression collapses to `1 − K/(K−1)` — negative, and
independent of how consistent the agent actually was. At K=5 it is −0.25 for every
task that is not unanimous.

The **reliability dashboard** states a different formula in prose:

```
consistency = (2p̂ − 1)²
```

described there as scaling on [0, 1] with no clipping and being smooth across the
range: 1 when the agent always agrees with itself, 0 at a 50/50 split.

**We implement `(2p̂ − 1)²`**, cite the dashboard page with an access date, and record
the paper's variant here with the derivation above so the choice is defensible from
first principles rather than from deference to either source. `DESIGN.md` §6.4
independently arrived at the same form before this survey.

## 4. Deliberately not taken

| Thing | Why not |
|---|---|
| `MODEL_PRICES_DICT` and the cache-tier overrides | No licence. And our own `rca/pricing/prices.yaml` is already better: it carries dates, versions and per-entry verification flags, where theirs is an undated Python dict. The earlier note calling it "worth copying" is superseded |
| `reliability_eval/` implementations | No licence. We implement from the paper |
| Their phase names and CLI shape | No licence. Our phase organisation and field names are our own |
| The Docent log-analysis rubric | Paper text, and the categories need rewriting for geoscience regardless |
| `hal_traces` | No licence set; not ours to redistribute |
| Submitting our results to their board | Archived 2026-07-01; submissions closed |

## 5. Ours, not theirs

Recorded here so the boundary is legible in both directions.

| Metric | Status |
|---|---|
| `abstention_accuracy` | **Contribution.** The HAL paper does not define abstention as a metric; it appears only as a benchmark instruction to return a blank string when the information is absent. Ours is typed, has a reference, and replaces a six-phrase substring test we wrote ourselves |
| `grounding_rate`, `overclaim_rate` | **Contribution.** Typed judgments against a passage or against a checker result, not a rubric. See [`../jev_scorers.md`](../jev_scorers.md) |
| `citation_fabrication_rate`, `cutoff_compliance` | **Ours.** Already computable from `citation_support` and the cutoff tests; this refactor surfaces them as named numbers |
| The integrity axis as a whole | **Ours.** HAL's safety dimension is PII, destructive operations and policy circumvention. The scientific analogue is fabricated citations, overclaimed results and licence or embargo violations. Only the structural principle — report it separately, never average it into the headline — is adopted |
| Every geoscience fault mode | **Ours.** FDSN 503s and timeouts, M2M auth failures, M2M partial returns, truncated miniSEED, empty streams; epoch vs ISO time, empty-location-code spelling, SEED id shape. The paper supplies the three perturbation *kinds*; the instances are domain work |

## 6. Where to cite

- `paper/refs.bib`: `kapoor2026hal`, `rabanser2026reliability`,
  `kapoor2024agentsthatmatter`.
- `paper/manuscript.md` Methods, where the reliability metrics are introduced.
- `docs/glossary.md`, on each adopted metric's entry.
- Docstrings in `src/repere/reliability.py`, naming the paper and equation, never a
  HAL source file.

## 7. Check before merge

Every row in §1 and §2 must name a paper section, an equation, or a documentation page
with an access date. Any row whose only source is the HAL repository is removed and
the metric dropped or re-derived. No comment in our code may point at a HAL source
file as its reference.
