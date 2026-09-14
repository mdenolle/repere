# Design constraints for FrugalMind from three sources: AI Agents That Matter, the Agentic Benchmark Checklist, and GEPA

Prepared 2026-09-14. Everything below was read from the arXiv PDFs (downloaded today, text extracted with `pdftotext`) and from a shallow clone of `gepa-ai/gepa` at commit `15ee314` (2026-09-11). Nothing was rerun; no experiment in any paper was reproduced. Page numbers refer to the arXiv PDF of the version stated. Items I could not confirm in the raw text are marked NOT VERIFIED.

Local copies: `<scratch>/prior/{2407.01502,2507.02825,2507.19457}.pdf` (+ `.txt`, `.raw.txt`), and `.../scratchpad/prior/gepa/`.

## 0. Identifier verification

| Requested | arXiv id | Resolves to | Version read | Status |
|---|---|---|---|---|
| AI Agents That Matter (Kapoor, Stroebl, Siegel, Nadgir, Narayanan) | 2407.01502 | same title, same authors | v1, 2024-07-01 (only version) | verified |
| Establishing Best Practices for Building Rigorous Agentic Benchmarks (Zhu, Jin, ... Kang; 25 authors) | 2507.02825 | same title | v5, 2025-08-07 | verified |
| GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning (Agrawal et al., 17 authors) | 2507.19457 | same title; PDF header "Accepted at ICLR 2026 (Oral)" | v2, 2026-02-14 | verified |
| GEPA repo | github.com/gepa-ai/gepa | README links the same arXiv id | HEAD 15ee314, 2026-09-11 | verified |

---

## 1. AI Agents That Matter (arXiv:2407.01502 v1)

### 1.1 The five findings (p.1-2, each tied to a section)

Quoted headline sentences, p.1-2:

1. "AI agent evaluations must be cost-controlled (Section 2)." Reason: LLMs are stochastic, so repeated calls raise accuracy; without a cost axis leaderboards reward "extremely costly agents just to claim they topped the leaderboard" (p.2).
2. "Jointly optimizing accuracy and cost can yield better agent design (Section 3)." Cost and accuracy as a Pareto curve; they modify DSPy to optimize both on HotPotQA.
3. "Model developers and downstream developers have distinct benchmarking needs (Section 4)." NovelQA case study; downstream evaluation should use dollar cost, not proxies such as parameter count.
4. "Agent benchmarks enable shortcuts (Section 5)." Four levels of agent generality, each needing a different holdout; WebArena/STeP case study.
5. "Agent evaluations lack standardization and reproducibility (Section 6)." Reproduction failures on WebArena and HumanEval (Table A6); "These errors inflate accuracy estimates."

Conclusion (p.11) restates them as: cost-controlled comparisons, separating model and downstream evaluation, preventing shortcuts with appropriate hold-outs, greater standardization.

### 1.2 Cost-controlled evaluation (Section 2, p.2-4; Table A1, p.20)

Argument: accuracy alone cannot identify progress because it can be raised by "scientifically meaningless methods such as retrying" (p.4). AlphaCode goes from ~0% to >15% with 1,000 retries and >30% with a million (p.3). Where the environment offers a correctness signal (test cases), sampling until pass is always available.

Method: re-run three published HumanEval agents with public code (LDB, LATS, Reflexion) and four baselines, five runs each on 164 problems, mean accuracy and mean total dollar cost, plotted as a convex Pareto frontier (Figure 1, p.4; footnote 2: two agents can be mixed with probability p). Prices: GPT-3.5-turbo-0125 at $0.5/$1.5 per M input/output tokens, GPT-4-turbo-2024-04-09 at $10/$30, April 2024 (Appendix A.1, p.20).

Table A1 (p.20), mean over 5 runs:

| Agent | Accuracy % | Total cost USD (164 problems) |
|---|---|---|
| LATS (GPT-4) | 88.0 | 134.50 |
| LATS (GPT-3.5) | 80.4 | 9.49 |
| LDB (GPT-4 gen, GPT-3.5 debug) | 91.0 | 2.19 |
| LDB (Reflexion, GPT-4) | 92.9 | 7.26 |
| LDB (GPT-4) | 93.3 | 6.36 |
| LDB (GPT-3.5) | 80.2 | 0.63 |
| GPT-4 zero-shot | 89.6 | 1.93 |
| GPT-3.5 zero-shot | 73.9 | 0.05 |
| Reflexion (GPT-4) | 87.8 | 3.90 |
| Warming (GPT-4), their baseline | 93.2 | 2.45 |
| Retry (GPT-4), their baseline | 92.0 | 2.51 |
| Escalation, their baseline | 85.0 | 0.27 |

Findings on p.3-4: "State-of-the-art agent architectures for HumanEval do not outperform simple baselines"; "For substantially similar accuracy, the cost can differ by almost two orders of magnitude"; Reflexion and LDB cost over 50% more than warming, LATS over 50 times more; escalation "strictly improves accuracy while costing less than half of LDB (GPT-3.5)". Whether debugging/reflection ("System 2") helps code generation "remains open" (p.4).

### 1.3 Trivial baselines (Section 2.2, p.3; Appendix A.1, p.21)

- Zero-shot GPT-3.5 and GPT-4, no agent architecture.
- Retry: call the model at temperature 0 up to five times if the problem's example tests fail (LLMs are not deterministic even at temperature 0).
- Warming: retry, raising temperature from 0 to 0.5 across attempts.
- Escalation: Llama-3 8B, then GPT-3.5, Llama-3 70B, GPT-4 on test failure.

They know of no paper comparing its agent to retry, warming or escalation on HumanEval (p.3). They used the LDB-modified HumanEval with machine-readable example tests for all 164 tasks (original: 161/164).

### 1.4 Joint optimization (Section 3, p.4-5)

Cost = fixed (one-time optimization of prompts/hyperparameters) + variable (per-run tokens). DSPy with a modified optimizer on HotPotQA: 53% lower variable cost at similar accuracy for GPT-3.5, 41% for Llama-3-70B; optimization cost recouped after 1,350 tasks (p.5). Generalizes to latency.

### 1.5 Model evaluation vs downstream evaluation (Section 4, p.6-7)

Model evaluation is a scientific question where proxies (parameters, FLOPs) are stable and fair. Downstream evaluation is procurement: "cost is the actual construct of interest"; proxies mislead (Mixtral 8x22B "active parameters" marketing vs Mixtral 8x7B costing twice Llama 2 13B on Anyscale, June 2024). Because prices change, "downstream evaluations of agents should include input/output token counts in addition to dollar costs" (p.7). NovelQA: asking all questions about a novel in one context favors long-context models; per-question, RAG is equally accurate and >20x cheaper (Table A5), but NovelQA shows RAG only 2x cheaper, a tenfold distortion. "Downstream evaluation benchmarks must be separate from, or at least variants of, model evaluation benchmarks."

### 1.6 Holdouts and shortcuts (Section 5, p.7-9; Table 1, p.8; Appendix C / Table A4)

| Level | Definition | What must be held out | Benchmarks with appropriate holdout (of 17) |
|---|---|---|---|
| Distribution-specific | one task, no shift modeled (US grade-school math) | in-distribution samples | 1/1 |
| Task-specific | one task, shifts incl. drift matter (book a flight, fix a GitHub issue) | out-of-distribution samples | 3/6 |
| Domain-general | any task in a domain (web browsing, tool use) | tasks | 1/8 |
| Fully general | across domains | domains | 0/2 |

Core principle (p.8): "the more general the intended generality of the agent, the more the held-out set should differ from the training set." A holdout counts as appropriate if it exists or intent is stated; 7 of 17 have neither. Responsibility is the benchmark developer's. Drift is the key shift for task-specific benchmarks; modeling it means collecting real site changes and keeping the held-out set secret (p.9). Sim2real (evaluate on the real Amazon as well as the clone) is another option. Many papers never state their generality level, which makes leaderboard results uninterpretable.

STeP case (5.1, p.9): top WebArena agent at 35.8% hardcodes per-task policies (append `/user/user_name` to the base URL for Reddit profile tasks); any URL change breaks it; with held-out tasks from unseen websites "the accuracy agents like STeP would be drastically lower". Section 5.2 adds that benchmarks do not model human-in-the-loop supervision.

### 1.7 Reproducibility (Section 6, p.10-11; Table A6)

1. No standard evaluation scripts; developers write their own, benchmark scripts have bugs.
2. LLM benchmarks repurposed for agents: HumanEval lacked example tests for 3/164 problems; Reflexion and LATS dropped them, LDB added tests; PapersWithCode mixes these.
3. Cost prevents CIs: SWE-Agent at $4/task on >2,000 SWE-bench tasks is >$8,000 per run; "agent evaluations are rarely accompanied by error bars"; several reported accuracies exceeded the maximum of their five runs, some baselines were below their minimum.
4. Environment interactions: WebArena's Reddit clone rate-limits posting, so tasks run back-to-back fail more, violating task-order invariance; affects STeP.
5. Bugs: LATS and STeP marked incorrect completions as correct and removed tasks (1 and 8).

Recommendation: an agent-evaluation framework analogous to HELM / LM Evaluation Harness (p.11).

### 1.8 Design constraints implied for FrugalMind (from AAM)

- Every scored run records per task: dollars, input tokens, output tokens, model calls, wall time, and the price table used, so cost can be recomputed later (Section 4). FrugalMind is a downstream evaluation, so dollars are the construct; store proxies too.
- Report accuracy-cost Pareto frontiers per tier; report optimization (fixed) cost separately from inference (variable) cost, and state the breakeven task count for any GEPA-optimized prompt (Section 3).
- Ship the trivial baselines as harness entries and require comparison to them: zero-shot single call; retry-until-checker-passes (T2's deterministic checker makes this exploit directly available, so retries must be counted in cost); warming; escalation across a model ladder; plus do-nothing and empty-answer agents (also needed for ABC R.13).
- Declare intended generality per task family and build the holdout accordingly: OOI coding agent is task-specific with drift as the main shift, so hold out OOD samples (other instruments, sites, time windows, changed endpoint versions); literature-RAG is closer to domain-general, so hold out whole task types and keep the set secret; metadata-RAG is task-specific, hold out OOD samples (new sensor families, vocabulary).
- Run each configuration at least five times with different seeds and report min/max or bootstrap CIs; FrugalMind is small enough to afford it.
- Provide the evaluation script yourself, agent-agnostic, no task removal, pinned dependencies; log every action and model call so misgraded tasks can be audited.
- Live-network tasks need explicit rate-limit budgets, randomized task order, and an order-invariance check.

---

## 2. Agentic Benchmark Checklist, ABC (arXiv:2507.02825 v5)

### 2.1 Definitions (Section 1, p.2)

- Outcome validity: "the evaluation result (e.g., tests or checks) truly indicates task success."
- Task validity: "a task should be solvable if and only if the agent possesses the target capability."

Built from 17 benchmarks used by major labs (Table 3), prior pitfall papers, and software-testing practice; item sources in Appendix C. Three parts: task validity (Figure 2, p.5), outcome validity (Figure 3, p.6), benchmark reporting (Figure 4, p.7). Ten open-source benchmarks assessed (Table 1, p.8): SWE-bench-Verified, SWE-Lancer, KernelBench, BIRD, Cybench, MLE-bench, GAIA, tau-bench, WebArena, OSWorld.

### 2.2 The full checklist (43 items: 10 T + 20 O + 13 R)

Requirement text is the paper's wording, lightly shortened; ids are the paper's. The evidence column is mine, for the FrugalMind audit table.

| id | group | requirement (paraphrase) | what evidence would satisfy it for FrugalMind |
|---|---|---|---|
| T.1 | Task validity / Tool | Versions of all tools (e.g., Python) are clearly specified. | Lockfile plus container digest per tier; versions stated in the task prompt where the agent installs/imports packages. |
| T.2 | Task validity / Tool | Required API tools are consistently accessible during evaluation. | Pre-flight health check of every OOI endpoint; rate-limit budget per run; HTTP status log per call. |
| T.3 | Task validity / Tool | Evaluation terminates or handles errors appropriately if an API becomes inaccessible. | Harness distinguishes "task void: endpoint down" from "agent failed"; aborts or voids rather than scoring 0. |
| T.4 | Task validity / Environment | Residual data or state fully cleared between runs. | Fresh container and scratch dir per task; no shared HTTP cache across tasks except the frozen fixture; test that consecutive tasks cannot see each other's files. |
| T.5 | Task validity / Environment | Agent completely isolated from any ground-truth information. | Oracle, reference outputs, rubric answers, gold citations outside the sandbox filesystem and network; separate credentials; CI scan that the sandbox cannot reach the reference store. |
| T.6 | Task validity / Environment | Setup does not change over time (e.g., no live website). | Default scoring mode replays frozen, checksummed HTTP fixtures; live mode is a separate labeled track with a dated manifest. |
| T.7 | Task validity / Implementation | Annotated ground truth verified for correctness. | Two independent annotators for T3 gold references and T4 rubrics; T1 oracle drift cross-checked against the independent measurement; disagreement log. |
| T.8 | Task validity / Implementation | Each task verified to be solvable. | Oracle passes the checker on 100% of tasks in CI; re-verified after any corpus/endpoint update. |
| T.9 | Task validity / Implementation | Includes an Oracle solver that automatically solves all challenges. | Oracle scripts for T1 and T2 run through the same harness; T3 gold retrieval set; T4 expert reference answer. |
| T.10 | Task validity / Implementation | Free of vulnerabilities exploitable to pass without completing tasks. | Pilot runs with outlier inspection; checker never reads agent-writable files; tests not overwritable; red-team run with a cheating agent. |
| O.a.1 | Outcome / info acquisition, whole or substring matching | Considers expressions semantically equivalent to ground truth. | Normalization rules (DOI case, whitespace, unit strings, instrument-id aliases) documented and unit-tested. |
| O.a.2 | Outcome / whole or substring matching | Handles redundant words used by agents. | Matching tolerates surrounding prose; tested with padded answers. |
| O.b.1 | Outcome / substring matching | Handles negation modifiers. | Test cases with "not", "no", "negative" around the gold string score 0. |
| O.b.2 | Outcome / substring matching | Robust against systematically listing all possible answers. | Precision term in the score; test with an agent that returns the entire candidate list. |
| O.b.3 | Outcome / substring matching | Ground truth sufficiently complex to prevent guessing. | Continuous values with tolerance or specific identifiers; guess-rate reported. |
| O.c.1 | Outcome / LLM-as-a-judge | Documented or experimental evidence of the judge's accuracy, self-consistency, and agreement with humans. | Pilot: judge vs expert labels, repeat-run self-consistency, Cohen's kappa vs humans; published. |
| O.c.2 | Outcome / LLM-as-a-judge | Designed to resist adversarial inputs and reward hacking. | Adversarial probe set (empty, verbose, rubric-echoing, judge-instructing answers) with expected scores; judge sees only the answer. |
| O.d.1 | Outcome / code gen, unit or E2E testing | Test cases verified for correctness and quality (e.g., by human). | Every T2 checker reviewed by a second person; passes oracle, fails a known-wrong solution. |
| O.d.2 | Outcome / code gen, unit or E2E testing | Test quality measured with objective metrics (coverage, cyclomatic complexity). | Branch coverage of checker over the reference; mutation-testing rate. |
| O.e.1 | Outcome / code gen, fuzz testing | Addresses potential edge cases. | NaN, gaps, time-zone edges, empty responses, duplicate timestamps. |
| O.e.2 | Outcome / code gen, fuzz testing | Comprehensive coverage of relevant input variations (types, memory layouts, value ranges). | Generator varies dtype, shape, sampling rate, value range; documented. |
| O.e.3 | Outcome / code gen, fuzz testing | Generates inputs the code under test is sensitive to. | Perturbing inputs changes the reference output. |
| O.f.1 | Outcome / code gen, E2E testing | Exercises all relevant parts of the code. | Workflow branches (fetch, parse, QC, compute) each covered by a task. |
| O.f.2 | Outcome / code gen, E2E testing | Prevents non-deterministic ("flaky") results. | Fixed seeds, float tolerances, no wall-clock timeouts in the pass/fail decision, replayed network; flakiness measured by re-running the oracle N times. |
| O.g.1 | Outcome / state matching | Ground truth includes all states achievable after success. | All acceptable output formats/paths enumerated. |
| O.g.2 | Outcome / state matching | Checks relevant and irrelevant states. | Checker verifies untouched files stay untouched. |
| O.g.3 | Outcome / state matching | Ground truth complex enough to prevent trivial modifications. | Do-nothing and random-write agents score 0. |
| O.h.1 | Outcome / multistep reasoning, answer matching | Specifies required answer formats in task descriptions. | T1 prompt states units, sign convention, precision, output field; parser assumptions documented. |
| O.h.2 | Outcome / answer matching | Minimizes success by random guessing. | Continuous answers with tolerance; chance-level score reported. |
| O.i.1 | Outcome / quality measure | Quality metrics that prevent exploitation (reward hacking). | Rubric score correlated with expert judgment; gaming strategies (length, keyword stuffing) shown not to raise it. |
| R.1 | Reporting / transparency | Fully or at least partially open-sourced. | Public repo with tasks, fixtures, checkers. |
| R.2 | Reporting / transparency | Open-source evaluation harness. | One-command run for any agent. |
| R.3 | Reporting / transparency | Measures against data contamination at release, such as a private held-out test set. | Secret test split; date-bounded corpus; canary strings. |
| R.4 | Reporting / transparency | Measures or plans to update challenges over time to avoid overfitting. | Written refresh schedule (new windows, instruments, rolling corpus date). |
| R.5 | Reporting / transparency | States the relationship between capabilities evaluated and constructs/outcomes measured. | One paragraph per tier: capability -> construct -> metric. |
| R.6 | Reporting / transparency | States the evaluation subject (a model or an agent framework). | Statement that FrugalMind evaluates agent systems (model + scaffold + prompt) at a stated cost. |
| R.7 | Reporting / flaw mitigation | Describes steps to prevent, identify, correct flaws. | Section listing the ABC audit and fixes. |
| R.8 | Reporting / flaw mitigation | Qualitative discussion of unavoidable flaws. | Known-limitations section (judge noise, endpoint drift). |
| R.9 | Reporting / flaw mitigation | Quantitative analysis of unavoidable flaws (e.g., ground-truth noise). | Judge-noise bound from the pilot; drift rate from fixture refreshes; annotator disagreement rate. |
| R.10 | Reporting / interpretation | Statistical significance metrics such as CIs. | Bootstrap CIs over tasks and seeds on every leaderboard number. |
| R.11 | Reporting / interpretation | Guidance on interpreting results given flaws. | Per-tier interpretation notes. |
| R.12 | Reporting / interpretation | Results of non-AI baselines (human experts). | A human expert or graduate student on a task sample, with time and cost. |
| R.13 | Reporting / interpretation | Results of trivial agents (e.g., one that does nothing). | Do-nothing, empty-answer, list-everything, retry-only agents on the leaderboard. |

Label notes: Figure 3 prints the last item "O.I.1"; the text (p.7) calls it O.i.1. Appendix D reports (SWE-Lancer, BIRD) use an "O.f.3" label absent from Figure 3. Section 2 says 7.7% (Lite) / 5.2% (Verified) of SWE-bench tasks pass without correct patches; Appendix D says 5.3% / 7.7%; that 5.2 vs 5.3 discrepancy is in the paper itself.

### 2.3 Scoring (Section 3, p.4; Section 5.1, p.7-8)

"We assigned 1 point to each satisfied item and 0 otherwise." Then "For each part of ABC, we calculated the average scores of applicable items." So three part-scores, each = satisfied applicable items / applicable items, shown as percentages in Figure 5 (p.8). Items tied to an evaluation method the benchmark does not use are excluded. No partial credit, no weighting. Per-benchmark numeric scores exist only as Figure 5 bars: NOT VERIFIED numerically. Headline: 7/10 violate task validity, 7/10 violate outcome validity, all 10 have reporting limitations; "80% of the benchmarks fail to acknowledge weaknesses in their design or implementation, and none satisfies every reporting criterion."

### 2.4 Failure examples (Sections 1, 2, 5.2, 5.3; Appendix D/E)

| Benchmark | Items violated | Failure | Quantified effect |
|---|---|---|---|
| SWE-bench-Verified | O.d.1, O.d.2 (T.7 per Sec. 2) | unit tests miss edge cases; incorrect patches pass | 24% of top-50 leaderboard positions incorrect (citing [31, 87]); 5.2% Verified / 7.7% Lite pass without correct patches (p.3) |
| tau-bench | O.b.3, O.g.3 | intentionally unsolvable tasks scored as success if environment unchanged; do-nothing agent passes | 38% of airline, 6% of retail; do-nothing "outperforms a GPT-4o-based agent"; overestimation 38% (p.8) |
| tau-bench | O.b.2 | verbatim DB text as ground truth via substring; dump-the-database agent passes | 2% airline, 3.6% retail; overestimation 40% (p.8) |
| WebArena | O.b.2, O.c.1 | substring ignores extraneous content; LLM judge accepts empty reply on "N/A" tasks | 1.4-5.2% overestimate (p.8) |
| WebArena | T.2 | site rate limits blocked agents | none given (p.3) |
| SWE-Lancer | T.5 (T.10) | tests in password-protected zip whose contents can be listed and overwritten; `assert 1 == 1` | 100% without solving anything (p.9) |
| KernelBench | O.e.1, O.e.2 | fuzzer varies values only, not shapes/memory layouts | correctness overestimated 31% absolute (p.9) |
| KernelBench | T.4 | ground truth left in GPU memory, readable out-of-bounds (citing Lange et al.) | none given (p.5) |
| OSWorld (chrome) | T.6 | 13/46 tasks broken by site changes; selectors in checkers | UI-TARS underestimated 28% absolute (p.9) |
| BIRD | T.4, T.9 | DB not read-only or re-initialized between runs; no oracle solver | T.9 in Appendix D; T.4 detail NOT VERIFIED in raw text |
| CVE-Bench (theirs) | O.g.1 | SQL-injection scored by SLEEP in the log, not execution | overestimation 32.5% (p.9) |
| CVE-Bench (theirs) | T.9 (found by oracle mock runs) | outbound server reachable from the same docker network | success fell 10% after gating; overall 33% absolute cut in overestimation (p.2, p.10) |

Overall: evaluation issues cause "under- or overestimation of agents' performance by up to 100% in relative terms" (abstract).

### 2.5 Issues most relevant to FrugalMind

(a) Live network calls. Section 4.1 (p.4-5): manage availability and rate limits (T.2); detect API interruptions and terminate "to keep benchmark users informed" (T.3); environment "fully reproducible and frozen at the time of benchmark release" (T.6); "Relying on dynamic resources, such as continually updated external websites, is not recommended." Evidence: OSWorld drift broke 13/46 tasks and underestimated the best agent by 28 points; WebArena rate limits caused spurious failures. Also T.4 (no cross-task residual state such as a shared HTTP cache), O.f.2, R.4, R.9.

(b) LLM-as-judge. O.c.1 (evidence of accuracy, self-consistency, human agreement), O.c.2 (adversarial resistance). Text (p.5): "the accuracy of LLM annotations varies across domains"; "recommend conducting pilot experiments to assess the accuracy and self-consistency of LLM judges." WebArena's judge accepted empty replies. No numeric threshold; satisfaction is binary. R.7-R.9 and R.11 then require documenting and quantifying residual judge noise. BIRD satisfies O.c.1 by evaluating its judge in its own Appendix A.8.

(c) Oracle / reference solution. T.7, T.8, T.9, T.5, T.10. The CVE-Bench case shows the oracle's second use: running it repeatedly through the harness surfaced a bug because "agents consistently passed the evaluation for this attack" (p.9). Cybench has an oracle for all tasks; SWE-Lancer/SWE-bench count gold patches as oracles; BIRD lacks one. For reference tests: O.d.1, O.d.2.

### 2.6 Design constraints implied for FrugalMind (from ABC)

- Treat T.6 as the central tension: the coding agent's live OOI fetches violate T.6 by construction. Two tracks: a frozen track replaying recorded, checksummed, dated HTTP responses as the scored default; a live track, explicitly labeled, with T.2 pre-flight checks, T.3 abort-on-failure, and re-validation against the frozen manifest so drift is measured (R.9), not silently scored.
- Run the T1/T2 oracle through the full harness in CI before every release and after every fixture refresh; require 100% (T.8, T.9). Run a deliberately cheating agent (reads reference paths, overwrites checker, returns everything) and require 0% (T.5, T.10).
- Keep every reference artifact outside the sandbox filesystem and network namespace with separate credentials; CI test that the sandbox cannot resolve the reference store (T.5).
- T4: before any LLM judge is used, pilot on an expert-labeled subset and publish judge accuracy, self-consistency, kappa vs the two human raters (O.c.1); run and publish the adversarial probe set (O.c.2). The planned inter-rater agreement satisfies O.c.1 only if the judge is compared to it.
- T3: normalized identifier match with a precision component so listing every candidate does not pay (O.a.1, O.b.2); corpus frozen and versioned (T.6, R.3).
- T2: second-person review of every checker, coverage/mutation metrics over the oracle, fixed seeds and tolerances, no wall-clock timeouts in pass/fail (O.d.1, O.d.2, O.f.2).
- T1: units, sign convention, tolerance and output format in the task text (O.h.1); continuous answers with tolerance; report chance level (O.h.2).
- Reporting: publish the ABC audit with per-part averages over applicable items, bootstrap CIs (R.10), trivial-agent rows (R.13), one human baseline (R.12), a refresh plan (R.4), and a stated subject: agent systems at a stated cost (R.6).
- Apply the checklist twice: to the leaderboard harness and to the GEPA optimization loop, because GEPA sees gold answers in feedback (3.9).

---

## 3. GEPA (paper arXiv:2507.19457 v2; repo gepa-ai/gepa at 15ee314)

### 3.1 Repo facts (verified from the clone)

| Field | Value | Source |
|---|---|---|
| License | MIT, copyright 2025 Lakshya A Agrawal | `LICENSE`, `pyproject.toml` |
| Python | `>=3.10, <3.15` | `pyproject.toml` |
| Package version at HEAD | 0.1.4 | `pyproject.toml` |
| Latest tag | v0.1.4 (8b0ce6c); HEAD 15ee314 (2026-09-11) is ahead of the tag | `git ls-remote --tags`, `git log` |
| Dependencies | none required; `gepa[full]` adds litellm (<1.92), tqdm, cloudpickle, datasets, mlflow, wandb | `pyproject.toml` |
| Integration point | `GEPAAdapter` protocol: `evaluate`, `make_reflective_dataset`, optional `propose_new_texts`, optional `batch_evaluate` | `src/gepa/core/adapter.py` |
| Entry points | `gepa.optimize(...)`, `gepa.optimize_anything(...)`, `dspy.GEPA` (DSPy repo) | `src/gepa/api.py`, README |

Paper: ICLR 2026 oral. Six benchmarks (HotpotQA, IFBench, HoVer, PUPA, AIME-2025, LiveBench-Math), Qwen3-8B and GPT-4.1-mini. Table 1 (p.8, Qwen3-8B): GEPA aggregate 54.85 vs GRPO 48.91 vs MIPROv2 47.84 vs baseline 45.23; GEPA budgets 1,839-7,051 rollouts per benchmark vs 24,000 for GRPO. Table 2 (GPT-4.1-mini): GEPA +12.19, GEPA+Merge +13.33, MIPROv2 +5.64, TextGrad +6.11. All GPT-4.1-mini experiments under $500; GEPA runs $86 (Appendix E.3, p.25).

### 3.2 Algorithm (Section 3, p.4-7; Algorithms 1-2, p.6)

Split D_train into D_feedback and D_pareto. Pool starts with the seed. Each iteration: select a candidate from the Pareto front (Algorithm 2), pick a module (round-robin), run on a minibatch of size b from D_feedback with tracing, call mu_f for score plus text, ask the reflection LM for a new prompt for that module, re-evaluate on the same minibatch; if the average improved, evaluate on all of D_pareto and add to the pool with parent records. Return the candidate with the best average on D_pareto. Optional system-aware merge (Appendix D.1, Algorithm 4, p.24). Rollout = one invocation of the system plus one evaluation by mu (Section 2, p.4).

### 3.3 (a) Scoring signal

- Type: `EvaluationBatch.scores: list[float]`, one per example, higher is better. Engine sums over the minibatch for acceptance (default `StrictImprovementAcceptance`: new sum > old sum; `strategies/acceptance.py`) and averages over the valset for tracking, Pareto fronts and the returned best (`FullEvaluationPolicy.get_best_program`, `GEPAResult.best_idx`).
- Range: not enforced. Adapter docstring: "Ensure your metric is calibrated accordingly or normalized to a consistent scale." But `perfect_score` defaults to 1.0 and `skip_perfect_score=True` skips reflection when all minibatch scores >= `perfect_score` (`reflective_mutation.py` ~line 448), so another scale must set `perfect_score` or disable the skip. Paper defines mu: Y x M -> [0,1] (p.4). `dspy.GEPA`: `failure_score=0.0`, `perfect_score=1.0`.
- Binary: allowed (paper uses exact match, pass rate). Cost: with minibatch 3 and strict improvement, a child is accepted only if it passes strictly more of the same 3 examples; `ImprovementOrEqualAcceptance` allows lateral moves.
- Multi-objective: optional `objective_scores: list[dict[str, float]]`; enables `frontier_type` "objective", "hybrid", "cartesian".
- Failures: never raise per example; return 0.0 plus a trajectory with the error; exceptions only for systemic failures (`raise_on_exception`).
- `EvaluationBatch.num_metric_calls` lets the adapter report the real evaluation count (else `len(batch)` is charged).

### 3.4 (b) Feedback text

- Contract: `make_reflective_dataset` returns per component a list of JSON records, recommended `{"Inputs", "Generated Outputs", "Feedback"}`, "passed verbatim to the instruction proposal prompt". The default template (`strategies/instruction_proposal.py`) inserts the prompt at `<curr_param>` and the records at `<side_info>`, then tells the reflection LM to "identify all niche and domain specific factual information about the task and include it in the instruction" and to capture any generalizable strategy.
- Required? Not checked by the library, but without it reflection sees only inputs/outputs. In DSPy, a float-only metric yields the default feedback "This trajectory got a score of {score}."
- Paper (p.5-7): mu_f "returns a numeric score and text feedback including details about the evaluation (like compiler error messages, failed rubrics, etc.)"; can be module-specific; human-written explanations can be attached as auxiliary feedback. Examples (Appendix E.1): IFBench lists constraints satisfied/failed; HoVer lists correct documents retrieved and still missing; PUPA gives the quality vs PII-leakage breakdown.
- Repo (`docs/docs/guides/adapters.md`, README): "Actionable Side Information"; include score, expected vs got, specific error analysis.
- DSPy adapter: `feedback_map[pred_name]` returns `ScoreWithFeedback(score, feedback, subscores)`; a predictor-level score differing from the module-level score is ignored with a warning naming "LLM-as-judge" as a likely non-deterministic cause; only the module-level score is used.

### 3.5 (c) Train / val / test

- API: `trainset` feeds reflection minibatches; `valset` is "used for tracking Pareto scores. If not provided, GEPA reuses the trainset." `dspy.GEPA` warns: "To ensure generalization and perform well on unseen tasks, please provide separate trainset and valset."
- The valset decides the Pareto front, the parent-selection distribution, and `best_candidate` (argmax mean valset score). It is a selection set, not a test set; its scores are optimistically biased.
- Paper protocol (Section 4, p.8; Appendix E.1, p.24-25; E.4, p.27): "standard train/validation/test split"; optimizers see train content and labels; may monitor validation scores but "direct access to the content of validation instances is restricted"; results on test. Train = D_feedback, validation = D_pareto. Splits: HotpotQA/HoVer 150/300/300, IFBench 150/300/294 with new OOD constraints as test, AIME 45/45 from 2022-2024 with AIME-2025 (30 x 5 repeats) as test, PUPA 111/111/221, LiveBench-Math 368 split equally. Generalization gap (val minus test) in Appendix H, Figure 16.
- FAQ: 80/20 when >200 examples, 50/50 below; valset "small but truly representative"; 30-300 examples recommended; works from 3.
- Cache namespacing: a distinct valset is a separate cache namespace so "held-out scores cannot be served from trainset rollouts at the same list index".
- Overfitting risks: (1) the reflection prompt deliberately copies dataset facts into the prompt and feedback carries gold answers, so prompts can memorize answers; (2) instance-level frontier keeps any candidate best on one val example, so small/unbalanced valsets give noisy selection; (3) the paper's inference-time search deliberately sets D_train = D_pareto = full task set to "overfit" (Section 5, p.12). GEPA provides no held-out test; you must.

### 3.6 (d) Budget and cost

- `max_metric_calls`: stops when `state.total_num_evals >= max_metric_calls`. Counter incremented by parent minibatch evals, child minibatch evals (`reflective_mutation.py`), and full-valset evals of accepted candidates (`engine._add_evaluated_program`); uses `num_metric_calls` if reported, else batch length; cache hits not charged with `cache_evaluation=True`. Whether the seed's initial valset evaluation is charged: NOT VERIFIED.
- Per iteration (FAQ): b parent evals + 1 reflection call + b child evals, plus |valset| if accepted; recommend budget >= 15-30 x len(valset). Paper: "The majority of GEPA's rollout budget is spent on validation" (Observation 1, p.9); train-only rollouts to optimum 79-737; to match GRPO's best validation, 102, 32, 6, 179 train rollouts on four tasks.
- `max_reflection_cost` (USD) on the reflection LM via litellm; exact only for `gepa.lm.LM` or model-name strings; plain callables report 0.0. GEPA does not track task-LM cost.
- Stoppers (`utils/stop_condition.py`): Timeout, NoImprovement, ScoreThreshold, MaxCandidateProposals, MaxTrackedCandidates, File (`gepa.stop`), Signal, Composite. One of `max_metric_calls`, `max_reflection_cost`, `stop_callbacks` is mandatory.
- DSPy: exactly one of `auto` (light/medium/heavy), `max_full_evals`, `max_metric_calls`.
- Paper budget alignment (E.4, p.27): GEPA capped to MIPROv2's rollout count per benchmark, within 10.15%; minibatch 3; merge at most 5 times.

### 3.7 (e) Multi-component prompts

- `Candidate = dict[str, str]`; at least one component. `module_selector`: "round_robin" (default) or "all". `reflection_prompt_template` may be a per-component dict. `make_reflective_dataset` gets `components_to_update`; `propose_new_texts` may update several components together.
- Merge (`use_merge`, default False in `gepa.optimize`, True in `dspy.GEPA`): combines module texts from two frontier candidates sharing an ancestor; accepted if merged subsample score >= the better parent.
- DSPy adapter: components are named predictors' instructions; with `enable_tool_optimization=True`, tool and argument descriptions are components under `tool_module:`.

### 3.8 (f) Pareto-front selection

- Paper (Algorithm 2, p.6; 3.1, p.7-8): per D_pareto instance record the best score and the set of candidates achieving it; drop candidates dominated by another in the union; sample with probability proportional to the number of instances led. Ablation (Table 3 per the WebFetch summary, NOT VERIFIED in raw text): Pareto +12.44% vs SelectBestCandidate +6.05% vs beam +5.11%; Figure 6 shows greedy stalling after one child.
- Code (`gepa_utils.select_program_candidate_from_pareto_front`, `strategies/candidate_selector.py`): same procedure; `frontier_type` "instance" (default), "objective", "hybrid", "cartesian". Alternatives: `current_best`, `epsilon_greedy` (0.1), `top_k_pareto` (k=5).
- Consequence: frontier diversity equals valset diversity; stratify the valset across task families.

### 3.9 Design constraints implied for FrugalMind (from GEPA)

- Every task returns a per-example float in [0,1] plus a feedback string. Per tier: T1, signed residual vs oracle drift in physical units, tolerance, units/sign check; T2, checker diff, stdout/stderr, exception text, HTTP statuses; T3, gold references retrieved, missed, date-bound violations; T4, failed rubric items with judge rationale, flagged noisy. Prefer graded scores (fraction of assertions, fraction of references) over pass/fail so 3-example minibatches discriminate.
- Three splits: GEPA-train (reflection), GEPA-val (Pareto and selection, FAQ-sized, stratified), and a FrugalMind test tier the optimizer never sees. Report val-test gap per optimized prompt. Test tasks must differ in the answers themselves (instruments, sites, time windows, corpus questions) because gold answers flow into the reflection LM.
- Audit optimized prompts before scoring: grep for gold values, instrument ids, endpoint strings, citation ids from train/val; any hit is an AAM shortcut and an ABC T.5 leak.
- Keep GEPA loops off the live network: optimize only on the frozen replay track (T.6, O.f.2); live nondeterminism breaks strict-improvement acceptance on 3-example minibatches.
- Budget: `max_metric_calls` ~15-30 x |val|; track task-LM calls and dollars inside the adapter; set `max_reflection_cost`; report `num_metric_calls` honestly when caching. Treat optimization spend as AAM fixed cost and the longer optimized prompt as added variable cost.
- Use separable components, e.g. `{"system_prompt", "data_access_rules", "citation_policy", "answer_format"}`, so round-robin reflection changes one thing at a time and audits are per component.
- Determinism: seed the adapter, fix temperature and model versions, make `evaluate` pure with respect to the sandbox; GEPA's `seed` only controls its own RNG.
- Run the ABC audit on GEPA's evaluation path too: its `evaluate` must satisfy T.4/T.5 exactly as the leaderboard harness does, or the optimized prompt inherits the leak.

---

## 4. Cross-cutting constraints by FrugalMind tier

| Tier | Primary ABC items | AAM items | GEPA score / feedback |
|---|---|---|---|
| T1 physics-verified | T.7, T.8, T.9, T.5, O.h.1, O.h.2, O.f.2 | cost + tokens per task; retry/warming baselines; OOD holdout by instrument/time window | score = 1 - clipped(residual/tolerance); feedback = residual, sign, units, fetch log |
| T2 execution-verified | O.d.1, O.d.2, O.f.1, O.f.2, T.1, T.4, T.10, T.6 (replay) | retry-until-pass is cheap here, count it; escalation ladder | score = fraction of assertions passed; feedback = failing assertions, traceback, stdout |
| T3 reference-verified | O.a.1, O.a.2, O.b.2, O.b.3, R.3, R.4, T.6 | held-out task types; secret test split | score = F1 over normalized ids with date-bound penalty; feedback = hits, misses, date violations |
| T4 judgment-dependent | O.c.1, O.c.2, O.i.1, R.8, R.9, R.11 | CIs; do-nothing and verbose baselines | score = rubric fraction; feedback = failed items and rationale; marked noisy |
| Whole suite | R.1-R.13; T.2, T.3 for the live track | Pareto plots, five seeds, agent-agnostic harness | three-way split; prompt audit for leaked answers; adapter-side cost tracking |

## 5. Items NOT VERIFIED

- ABC per-benchmark numeric scores (Figure 5 bar chart only).
- ABC BIRD T.4 detail, only from the WebFetch summary.
- GEPA Table 3 ablation numbers (+12.44 / +6.05 / +5.11), only from the WebFetch summary of the HTML version.
- Whether GEPA charges the seed's initial valset evaluation against `max_metric_calls`.
- The report file itself was not written: the harness refused `Write` for report files from a subagent. The parent should save this text to `<scratch>/report_papers_aam_abc_gepa.md`.