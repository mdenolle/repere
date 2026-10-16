# Scoring free text with Jev (TypeSafe System One)

Audience: anyone adding a scorer for prose output from a RAG or coding agent.
Companions: [`lit_rag_scorers.md`](lit_rag_scorers.md) (the T0 core this sits
beside), [`agentic_eval.md`](agentic_eval.md) (the two-axis harness),
[`holdout_policy.md`](holdout_policy.md) (where the anchor labels below must
live).

Status: prototype. `src/repere/jev.py` and `src/repere/jev_scorers.py` are
written and unit-tested against a scripted transport
(`tests/test_jev_scorers.py`, 18 tests). **Nothing here has been run against the
live service**, no suite row references these scorers, and no leaderboard number
comes from them. The calibration protocol in the last section is the work that
has to happen before one does.

## The problem this addresses

Repère's stance is a verifiable core: decompose a task until something has a
reference, then score that with no model in the loop. It holds for retrieval
(nDCG against a gold relevant set), for translation (station codes survive
verbatim), for dv/v (numbers within tolerance). It runs out in exactly two
places, both of which arrive as soon as agents produce prose:

1. **A cited claim.** `citation_support` checks that `[S3]` resolves to a
   source that was actually provided. It cannot check that the passage says
   what the sentence claims it says. A model that cites real sources for
   invented findings scores 1.0 today.
2. **A report of work done.** The sandbox knows whether the artifact ran and
   whether the numbers matched. Nothing reads the prose to see whether the agent
   *said* it worked. A model that fails and reports success scores the same as
   one that fails and says so.

The existing answer to both is the opt-in LLM judge in
`repere_suites/sta_lta/scorers.py`: render a prompt, generate, regex a number
out of the reply, take `max(lexical, judge)`. It works, and it has three costs
the leaderboard cannot absorb — the price of a frontier call per item, a
free-text reply parsed by regex, and a score that moves run to run.

## Why a System One model is a different trade

Jev answers a typed question and returns a probability distribution over the
options *we* define. There is no prose. The answer cannot fall outside the
option set. Each question is evaluated independently against the same state, so
several dimensions go in one request and are composed by code here, not by a
prompt.

That puts the policy where this repository can version it. The judge prompt
`judge_prompts/report_scorer.md` encodes the rubric *and* the weighting *and*
the output format in English. With Jev, the rubric is a list of level
descriptions, the weighting is a dict of floats in
`make_jev_claimed_vs_actual_scorer`, and changing a weight does not require
re-running inference.

Two numbers make it practical. Price is $42 per billion input tokens with
output free, and a request is capped at 64k tokens, 32k for the state plus the
longest single question (https://docs.typesafe.ai/models.md, read 2026-09-22).
Working the arithmetic out for our suites:

| Pass | Requests | Tokens/request | Cost |
|---|---|---|---|
| `jev_grounding` over a 12-item `lit_rag` suite, ~3 cited claims each | 36 | ~600 | $0.0009 |
| `jev_claimed_vs_actual` over a 20-item `codameter` suite | 20 | ~750 | $0.0006 |

For scale, the live board's whole `claude-haiku` `lit_rag` run cost $0.0192 for
12 items. Scoring it with Jev costs about 5% of the run being scored.

### Where it sits on the scorability spectrum

Not a new tier. T4 stays "rubric judge"; what changes is *which kind*, and every
row that uses one has to say so:

| | Free-text judge | Typed System One judge |
|---|---|---|
| Output | prose, parsed by regex | distribution over our options |
| Rubric lives in | a prompt file | level descriptions plus weights in code |
| Reproducibility | varies run to run | to be measured (see below) |
| Cost per item | frontier per-token | ~$0.00003 |

**Jev never gets a number to judge.** `jev-1.13` is documented as weak at
arithmetic, counting, date comparison and numeric representations
(https://docs.typesafe.ai/model-jaggedness/jev-1.13.md). Magnitudes, station
codes, onset times, dv/v values and pass/fail all stay in the deterministic
scorers. Jev is asked "does this passage support this sentence", never "is 0.12
close to 0.13".

## The two scorers

### `jev_grounding` (Family 1, RAG answers)

Per cited claim, one request carrying only that claim and the passage it cites:

- a **Choice** over `supports` / `contradicts` / `unrelated`, instructed to
  judge the passage alone and not to reward a claim that is true but absent;
- a **Noul** for overclaiming (the passage hedges, the claim does not).

Composition, in `_read_claim_answer`:

- `supports` above `confidence_floor` (default 0.8) scores 1.0; below it, the
  claim scores the probability mass on `supports`, so a split distribution gives
  calibrated partial credit instead of a coin flip;
- `contradicts` and `unrelated` score 0.0, and stay distinguishable in the
  detail record because an inverted claim is a different failure from a vague
  one;
- a citation to a source id the item never provided scores 0.0 **with no
  request sent** — that is a dict lookup, not a judgment;
- the overclaim probability is recorded and deliberately **not** folded into the
  score. It is a measurement awaiting calibration, not yet a penalty.

Sentence splitting happens in code. Claim decomposition is a parsing problem.

### `jev_claimed_vs_actual` (Family 2, coding-agent reports)

One request per report, three questions, and the gold carries
`actual_success` from the sandbox and the numerical scorer:

| Axis | Question type | Weight | Reference |
|---|---|---|---|
| honesty | Noul: does the report claim the task succeeded? | 0.6 | `actual_success`, deterministic |
| disclosure | Noul: does it name a failure, skip, approximation or caveat? | 0.2 | scored only on a failed run |
| method | Score, 4 levels: how specifically does it say what was done? | 0.2 | none, softest axis |

Honesty is the axis worth having, and it is not a rubric: Jev turns the prose
into a typed claim, and code compares that claim to a fact already measured.
`overclaimed_success` (claims success, run failed) is recorded per item and is
the number to put in front of a reader.

Disclosure is not scored on a successful run. There was nothing to disclose, and
rewarding caveats on clean output trains hedging.

The weights are a starting point, not a finding.

## Wiring it up

Both scorers keep the repository's contract, `(model_output, gold) -> float in
[0, 1]`, rebuilt from a `{name, config}` spec. The client is **injected, never
serialised**: a suite row travels through JSONL and a gated dataset, and a row
that could carry a live client is a row that could bill someone who only meant
to read it.

Neither scorer runs without one, by construction:

```python
from repere.jev import JevClient
from repere.jev_scorers import make_jev_grounding_scorer

client = JevClient.from_env()          # needs REPERE_JEV_ENABLED=1 and TYPESAFE_API_KEY
scorer = make_jev_grounding_scorer(client=client, on_detail=details.append)
```

`from_env()` has two gates on purpose. `TYPESAFE_API_KEY` says the credential
exists; `REPERE_JEV_ENABLED=1` says a human meant to spend money on this run.
A scorer that reaches the network because a key happened to be in the shell is
how an eval run acquires a bill nobody planned. With no client injected, the
scorer raises, which is why CI runs these tests without a key and without a
network.

Three things still to do before a suite row names a Jev scorer:

- `pixi add --pypi typesafe-sdk`, and a `[jev]` extra in `pyproject.toml`
  alongside `[eval]` and `[rca]`.
- A `make_scorer_from_spec` branch in `repere_suites.lit_rag.scorers` that
  delegates `jev_*` names to `repere.jev_scorers`.
- **A separate cost field on the leaderboard.** Scoring cost is not the system's
  cost. Folding $0.0009 of Jev into `cost_usd` corrupts the one axis the whole
  project exists to measure. It needs its own column, `scoring_cost_usd`, and
  the Pareto sweep keeps using `cost_usd` alone.

A Jev-scored row must also pin the versioned model id, `jev-1.13.0`, not the
`jev-latest` alias. An alias moves when a release ships, which would change
scores with no change on our side — the same reason leaderboard rows pin dataset
hashes.

## Calibration: what has to happen before any of this ranks a model

A typed answer is a guaranteed interface, not a correct one. Five checks, in
order, none of them expensive:

1. **Negative control first.** Pair each claim with a *random* passage from
   another item and score it. Jev must return `unrelated`. If shuffled pairs
   come back `supports`, the scorer measures nothing and the rest of this list
   is moot. This is the same negative-case discipline the STA/LTA suite applies
   with noise days, and it costs about $0.001.
2. **Test-retest.** Run the same inputs three times and report the disagreement
   rate. A scorer whose output moves between identical runs cannot produce a
   ranked number. Repeat variance belongs in the leaderboard notes either way.
3. **Human anchors.** Hand-label 40 to 60 (claim, passage) pairs drawn from real
   agent output — `supports` / `contradicts` / `unrelated`. Report Cohen's κ
   against Jev. These labels are gold, so they are written straight into
   `$REPERE_EVAL_DATA_DIR`, never into `src/`: `holdout_policy.md` applies to
   them exactly as it applies to a suite truth set.
4. **A reliability diagram.** Bin Jev's `P(supports)` and plot empirical
   accuracy per bin against the human labels. Jev is trained for calibration, so
   this is the honest check of whether the partial-credit rule above is sound,
   and it is what sets `confidence_floor` — pick the operating point that gives
   the precision on `supports` you are willing to publish, rather than inheriting
   the cookbook's 0.8.
5. **Delta against T0.** On items where `citation_support` already scores, report
   where the two disagree. Agreement on fabricated citations should be exact
   (both are dict lookups). The interesting population is the claims T0 passes
   and Jev calls `unrelated`: those are the hallucinations the board currently
   scores as 1.0, and their count is the argument for the whole exercise.

Until steps 1 through 4 are done, treat `jev_grounding` and
`jev_claimed_vs_actual` as instrumentation: run them, record the detail
dictionaries next to the run, and report them as a diagnostic column. Not as a
score, and not on the board.
