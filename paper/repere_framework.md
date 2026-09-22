# When Does Scaffolding Substitute for Scale?
## A cost-aware, rigor-preserving evaluation framework for scientific AI agents

**Marine Denolle**
*University of Washington, Department of Earth and Space Sciences*

> **SUPERSEDED.** The submission target is Nature Machine Intelligence and the
> canonical manuscript is now `paper/manuscript.md` (built with `make`). This
> file is retained as the original framework draft; do not edit both. Any claim
> corrected here must be corrected there too.

**Status:** working draft (v0.1). Framework paper. The evaluation suite is an
MVP demonstration; additional evals are in preparation (§8).

---

## Abstract

AI agents are entering the scientific workflow faster than our ability to check
them, and the evidence offered is usually a demonstration. A research group
facing an adoption decision does not need to know whether a frontier model is
impressive; it needs to know **the cheapest configuration that clears its
scientific quality floor** — and whether that configuration is one it is
permitted to run on its own data.

We argue that evaluation for AI-for-science must therefore be **cost-aware** and
**scaffolding-aware**, and that neither property can be retrofitted onto a
leaderboard that reports accuracy alone. We present Repère, a framework built
on four commitments: (i) *quality floors and frugality* — cost is a first-class
axis and the interesting winner is the cheapest system that clears the floor;
(ii) a **scorability spectrum** that pushes every task as far toward a
deterministic reference as it will go, admitting an LLM judge only as a
last-resort fallback; (iii) **negative-case discipline**, in which an instance
with no signal is a first-class item, so confident hallucination is penalised
rather than invisible; and (iv) **skill-conditioned evaluation**, in which the
object of measurement is not a model but a *(model, scaffolding)* pair, and the
**skill lift** — the change in score attributable to domain guidance alone — is
reported as a quantity in its own right.

We instantiate the framework on two geoscience evaluations spanning two of three
proposed eval families, and run it live against four open 7–8B models executed
locally and one cloud model (410 inference calls; USD 0.14 total). The
demonstration yields a decision rule that we did not anticipate and that we
believe generalises: **whether scaffolding substitutes for scale depends on the
kind of task.** On a parameter-selection task, a domain skill lifts free local
models to a perfect score, matching the cloud model at zero marginal cost. On a
code-generation task, the same models fail regardless of scaffolding — they
import the correct library functions and then hand-roll a broken implementation —
and only the cloud model produces working code. We also report a methodological
result of independent interest: our own *simulated* leaderboard confidently
reported a plausible score on a task that live models score zero on, because the
task was ill-posed. No amount of harness engineering surfaces that; only a live
run does.

---

## 1. Introduction

The adoption question a laboratory actually faces is narrow and practical:

> *Given this task, this budget, and this data-governance constraint, what is the
> cheapest system that produces science I am willing to sign my name to?*

Existing benchmarks answer a different question. They rank models by capability
on tasks chosen for discriminative power, report accuracy, and treat cost — when
they report it at all — as an appendix. This is reasonable for tracking frontier
progress and useless for the adoption decision, for three reasons.

**Cost is not a footnote; it is half the decision.** A group that cannot spend a
frontier-model call on every step of a workflow needs to know where a cheap model
suffices. A leaderboard on which every entry clears the bar cannot tell it,
because the cost axis is decoration when nothing fails.

**The unit of deployment is not a model.** Laboratories do not deploy models;
they deploy models *plus scaffolding* — a system prompt, a domain skill, a tool
harness, an agent loop. Benchmarks that hold scaffolding fixed measure something
nobody ships. The interesting and actionable quantity is how much a given piece
of scaffolding *moves* a given model, and whether that movement is enough to
substitute for a more expensive one.

**Much scientific data cannot leave the building.** Embargoed catalogues,
pre-publication waveforms, collaborator data under agreement: for a large class
of real work, the API models are the ones a group is *not permitted* to use. A
benchmark that measures only closed API models is silent about the tools a lab
may actually run.

Repère is our attempt to build the evaluation instrument that these three
observations imply.

### 1.1 Contributions

1. **A framing**: cost-aware, quality-floor evaluation for scientific agents, in
   which the reported winner is the *cheapest system clearing the floor* rather
   than the highest scorer (§3.1).
2. **The scorability spectrum**: a discipline for constructing scientific evals
   that maximises verifiability and minimises judge noise, with an explicit
   ordering of scorer types and a rule — push every task as far up the ladder as
   it will go (§3.2).
3. **Negative-case discipline**: instances with no signal as first-class items,
   making confident hallucination a scored failure (§3.3).
4. **Skill-conditioned evaluation and *skill lift***: measuring the
   *(model, scaffolding)* pair and reporting the lift attributable to domain
   guidance as a primary quantity (§3.4).
5. **A three-family taxonomy** of scientific evals — document-based,
   software-agent, and research-workflow (trajectory-scored) — with a scoring
   strategy appropriate to each (§3.5).
6. **Contamination control by secret generator seed**: a hidden test split for
   *generated* benchmarks in which the generator is public and only the seed is
   secret, so the benchmark remains auditable while its answers remain
   unreconstructible (§3.6).
7. **An empirical decision rule** from a live demonstration: scaffolding
   substitutes for scale on parameter-selection tasks but not on code
   generation (§6).
8. **A methodological warning**: simulated evaluation harnesses can and do report
   confident scores on ill-posed tasks (§6.3).

Contributions 1–6 are the framework and are the primary claim of this paper.
Contribution 7 is a demonstration on a deliberately small MVP suite (§7 states
the limits plainly). Contribution 8 is a cautionary result we think the community
needs.

---

## 2. Position: what a scientific evaluation must measure

We take a scientific evaluation to be adequate only if it reports, jointly:

- **Correctness against a reference**, at the strongest form of verification the
  task admits — not a plausibility judgement.
- **Cost**, in currency, for the configuration that produced the score.
- **Reproducibility**, such that the number means the same thing next month:
  pinned environments, versioned scaffolding, and a truth set that cannot have
  been trained on.

Related efforts each satisfy some of this. Capability leaderboards (HELM and
successors) establish breadth but treat cost as secondary and scaffolding as
fixed. Agentic benchmarks (SWE-bench, GAIA) evaluate systems rather than models
and take execution seriously, which we build on directly — our substrate is
Inspect-aligned for this reason (§4).

**AstaBench** is the closest prior art and must be stated precisely rather than
caricatured: it benchmarks agents on scientific research tasks *and explicitly
accounts for model cost and tool access* as confounding variables. We therefore
do **not** claim that cost has been ignored. We differ in what we do with
scaffolding: AstaBench *controls* tool access so that agents can be compared
fairly, whereas Repère *varies* domain scaffolding in order to measure what
it buys, reporting the resulting skill lift as a primary quantity. One asks which
agent is better under matched conditions; the other asks which conditions a
laboratory should buy.

Domain scientific benchmarks establish task realism but typically score with
rubrics or human judgement, which reintroduces exactly the noise a scientific
claim cannot tolerate.

Repère's position is that these are not three separate desiderata to be
balanced but one instrument to be built: **an eval is only decision-useful if the
cost axis can discriminate, and the cost axis can only discriminate if the board
contains systems that fail.**

This has an uncomfortable corollary that we adopt deliberately: **the benchmark
must include models that are not good enough.** A board populated entirely by
frontier models is one on which the frugality question cannot even be posed.

---

## 3. The framework

### 3.1 Quality floors and frugality

Each task carries a **quality floor**: the score below which the output is not
scientifically usable. The floor is a property of the task and the discipline,
not of the model — it is set by what a reviewer would accept.

Evaluation then reports, for each *(model, scaffolding)* configuration, both the
score and the cost, and the recommended system is the **cheapest configuration
clearing the floor**. Cost is measured as realised token spend; locally-executed
open-weight models are recorded at zero marginal cost, which is not an accounting
convenience but the actual economics of running a model on hardware a lab already
owns.

The natural visualisation is a cost-vs-performance plane in which better systems
lie up and to the left, and in which a scaffolding intervention is an *arrow*
(§3.4).

### 3.2 The scorability spectrum

The central difficulty in evaluating open-ended scientific work is not obtaining
a number; it is trusting one. We therefore order scorer types by verifiability
and impose a construction rule.

| Tier | Gold form | Scorer | Judge noise |
|------|-----------|--------|-------------|
| **T0** deterministic | exact or structured value | field match with tolerance; term preservation; citation resolution | none |
| **T1** numerical | reference array or scalar | tolerance / correlation / F1 against a reference pipeline output | none |
| **T2** perceptual | reference artifact | structural similarity against a golden figure | low |
| **T3** trajectory | reference process or DAG | node/edge agreement over the call graph | low–moderate |
| **T4** rubric | criteria, no single gold | LLM judge | high |

> **Construction rule.** Push every task as far *up* this ladder as it will go.
> Admit T4 only when no lower tier can express the check, and then only as a
> fallback whose disagreement with the deterministic score is itself reported.

This is a discipline, not a taxonomy: it changes how tasks are *written*. A
literature task that looks irreducibly T4 ("review this section") frequently
decomposes into a T0 retrieval component (are the cited passages the right ones?),
a T0 grounding component (does every citation resolve to a provided source?), and
only a small genuinely-T4 residue. Applying the rule shrinks the judged surface,
and with it the noise.

### 3.3 Negative-case discipline

An evaluation that contains only instances where something is present measures
sensitivity and is blind to fabrication. We therefore require that every eval
family carry **negative cases** — a time window with no earthquake, a query with
no supporting source, a goal whose correct plan is a single call — for which the
correct answer is an explicit *nothing*.

This is not a fairness nicety. In the demonstration below, three of eleven
detection cases are noise-only, and a model that reports an event in them is
penalised exactly as a model that misses a real one. Confident hallucination is
the failure mode a scientist most needs a benchmark to catch, and it is precisely
the one that a positives-only benchmark rewards.

### 3.4 Skill-conditioned evaluation and *skill lift*

We define a **skill** as versioned, human-authored domain guidance attached to a
task: not a prompt hack, but the thing a senior colleague would tell a new student
before they touched the data. A skill has a name, a semantic version, and a
change history, and every reported score records the exact skill version that
produced it.

An eval is run under **injection modes** — at minimum `none` (no skill) and
`full` (skill loaded) — and we define

> **skill lift** := *score*(model, skill) − *score*(model, none)

as a first-class reported quantity. This makes the object of measurement the
*(model, scaffolding)* pair rather than the model, which is what laboratories
actually deploy.

Skill lift also makes a specific economic claim testable: if a cheap model's lift
carries it above the quality floor, the expensive model is not required. On the
cost-vs-performance plane, a skill is an **arrow** from the unskilled to the
skilled configuration; for a locally-run model the arrow is *vertical*, because
its cost does not move. The visual asymmetry between a vertical free arrow
reaching the floor and a horizontal paid one is the entire thesis in one figure.

### 3.5 Three families of scientific evaluation

Scientific work is not one kind of task, and a benchmark that covers only one
gives a laboratory a distorted picture. We propose three families, each with a
characteristic scoring strategy:

1. **Document-based.** Reading and reasoning over the literature: review,
   critique, translation, interpolation, retrieval-augmented QA, figure
   interpretation. Scored predominantly at T0 by decomposition — retrieval
   metrics, domain-term preservation, citation resolution — rather than by rubric.
2. **Software-agent.** Agents that drive real scientific software: write the
   detector, configure the pipeline, produce the data product. Scored at T1–T2 by
   sandboxed execution and numerical regression against a reference within
   tolerance. This is where most of a computational group's day actually goes.
3. **Research-workflow.** Orchestrators that decide which sub-agents to call, in
   what order, with what dependencies. Scored at T3 on the **trajectory** — the
   realised call DAG against a reference — because an orchestrator that reaches
   the right answer through redundant fan-out has failed at the thing being
   evaluated. Frugality is a scored dimension here, not a framing, since
   orchestration is where cost explodes.

### 3.6 Contamination control: public generator, secret seed

A benchmark whose answers are public measures memorisation. The standard remedy
is a hidden test split, but for *generated* benchmarks it is easy to implement
this incorrectly: if the generator and its parameters are published, withholding
the generated file protects nothing, since anyone can reproduce it exactly.

We therefore locate the secret in the **generator seed** rather than the data.
The generator is public and auditable; the public `validation` split ships with
the framework so that anyone can develop against it and reproduce the
demonstration on a laptop. The `test` split — the answers a ranked score is
computed from — is synthesised from a **secret master seed** from which every
instance parameter (event delay, amplitude, noise level, inter-event gap) is
drawn. The seed is stored with the gated dataset and never committed. Without it
the hidden answers cannot be reconstructed even by an adversary holding the
generator and the underlying public data.

This yields a property we consider important: **the benchmark is simultaneously
fully auditable and genuinely hidden.** Reviewers can inspect exactly how the
truth set is made without thereby learning the answers.

---

## 4. Implementation

Repère is implemented in Python on an Inspect-aligned substrate (`Task` /
`Solver` / `Scorer`), which buys interoperability with the wider agent-evaluation
ecosystem. Three design choices are load-bearing.

**Scoring is a declarative specification, not code.** Every benchmark row carries
a serialisable `scorer_spec` — a name and a configuration — from which the scoring
callable is reconstructed at score time. A row is therefore self-contained and can
be scored by a third party, or by a server holding hidden answers, without running
the author's Python. This is what makes server-side scoring of a hidden split
possible at all, and it is what lets a contributed eval be trusted without
executing contributed code at scoring time.

**Execution is sandboxed and pinned.** Model-generated code runs in a pinned
container; the environment is a reproducibility boundary, so that a score means
the same thing on another machine and next year. Per-suite images allow heavy
scientific dependencies without inflating the common environment.

**Everything that affects a score is versioned**: the truth set, the skill, the
scorer spec, the model, and the sandbox image, all recorded on the row that
carries the score.

---

## 5. Demonstration: an MVP suite

We instantiate two evaluations from the software-agent family. **They are
deliberately simple**; the purpose is to exercise the framework end-to-end and to
show that the instrument discriminates, not to survey the space of geoscientific
tasks. Additional evaluations, contributed by members of our group, are in
preparation (§8).

**E1 — STA/LTA detection (code generation).** Given a seismic waveform and
detector parameters, the agent must *write* a short-term-average / long-term-average
detector; the sandbox executes its code and grades the trigger onsets it reports
against reference onsets (F1 with a 1.5 s tolerance). Cases are synthesised from a
real 2019 M7.1 Ridgecrest recording by seeded transforms. 11 public cases: 8
positive, **3 noise-only negatives**.

**E2 — dv/v processing (parameter selection).** Given a monitoring target
(volcano, fault, landslide, groundwater, cryosphere, geothermal), the agent must
choose the six coupled parameters of an ambient-noise relative-velocity-change
pipeline — estimator, frequency band, coda window, stack, reference, coherence
gate. Scoring is performed by `codameter`, which runs the proposed configuration
on a hidden synthetic and grades recovery of the known dv/v. 20 validation cases.

**Skills.** Two skills, authored as domain guidance and versioned:
`stalta-detection` (v0.3) and `dvv-processing` (v0.1). Each eval is run under
`none` and `full` injection.

**Models.** Four open-weight 7–8B models executed locally via Ollama at zero
marginal cost (`qwen2.5:7b`, `llama3.1:8b`, `deepseek-r1:7b`, `olmo2:7b`) and one
cloud model (`claude-haiku-4.5`) as a reference ceiling.

**Protocol.** Live inference throughout: real prompts, real skill injection,
model-generated code executed in the sandbox, deterministic scoring, cost from
realised token usage. 410 calls, zero harness errors, USD 0.135 total spend.

---

## 6. Results

### 6.1 Parameter selection: scaffolding substitutes for scale

| Model | none | +skill | lift | cost |
|---|---|---|---|---|
| claude-haiku-4.5 | 0.19 | **1.00** | +0.81 | $0.0350 |
| **qwen2.5:7b** | 0.38 | **1.00** | +0.62 | **$0.0000** |
| **llama3.1:8b** | 0.49 | **1.00** | +0.51 | **$0.0000** |
| deepseek-r1:7b | 0.23 | 0.85 | +0.62 | $0.0000 |
| olmo2:7b | 0.00 | 0.79 | +0.79 | $0.0000 |

Two free, locally-executed 7–8B models reach a **perfect score with the domain
skill, matching the cloud model at zero marginal cost.** The skill is doing
substantial work for every model — the lift ranges from +0.51 to +0.81 — and the
weakest model gains the most. On this task, the frugal configuration is not a
compromise; it is *equivalent*.

### 6.2 Code generation: scaffolding does not substitute for scale

| Model | none | +skill | lift | cost |
|---|---|---|---|---|
| claude-haiku-4.5 | 0.56 | **0.76** | +0.20 | $0.0728 |
| qwen2.5:7b | 0.10 | 0.10 | 0.00 | $0.0000 |
| llama3.1:8b | 0.10 | 0.10 | 0.00 | $0.0000 |
| olmo2:7b | 0.10 | 0.10 | 0.00 | $0.0000 |
| deepseek-r1:7b | 0.00 | 0.10 | +0.10 | $0.0000 |

Every 7–8B model fails, with or without the skill. The score of 0.10 is
diagnostic rather than merely low: under our staged scorer it corresponds exactly
to *"produced a code block that never executed successfully and never reported a
result."* Inspection of the generated code shows a consistent failure mode — the
models **import the correct library functions and then decline to use them**,
hand-rolling a windowed-average loop that terminates in an `IndexError`:

```python
from obspy.signal.trigger import classic_sta_lta, trigger_onset   # imported...
...
for i in range(len(waveform) - sta_samples):                      # ...then ignored
    lta_trace[i + lta_samples // 2] = np.mean(waveform[i:i + lta_samples])
# IndexError: index 1001 is out of bounds for axis 0 with size 1001
```

The skill explicitly instructs them to use the library. They do not comply.

The cloud model's behaviour is instructive in the other direction. Unskilled it
scores **0.56 — precisely the score of a canonical reference implementation
(0.559)**: it writes the textbook detector, which re-triggers on the seismic coda
and therefore reports one true onset and several artefacts, collapsing precision.
Loaded with the skill, which teaches coda declustering, it reaches **0.76**. It
*acts on* the guidance. The 7–8B models, given the same guidance, cannot.

### 6.3 The decision rule

> **Whether scaffolding substitutes for scale depends on the kind of task.**
> Where the task is *selection among domain choices*, a well-authored skill lifts
> a free local model to frontier parity, and paying for a frontier model buys
> nothing. Where the task requires *writing correct numerical code*, no skill
> rescues a model that cannot write it, and the frontier model is not optional.

For a laboratory, this is directly actionable: run configuration and
parameter-selection work on local open-weight models with good domain skills, at
zero marginal cost and with data that never leaves the building; reserve paid
frontier calls for code generation. It also suggests where scaffolding research
has the most headroom — an agent loop that lets a small model *see its own
traceback and retry* attacks exactly the failure mode in §6.2, and we identify
this as the most promising next experiment.

### 6.4 A methodological warning: the simulator lied

Before running live models we populated the leaderboard with a *simulated*
harness — deterministic per-model competence profiles emitting canned answers —
in order to exercise the pipeline without a GPU. It reported a plausible and
internally consistent **0.36 → 0.82** on the detection eval.

Live models scored **0.00 on every item.** The task, as originally written, pasted
~1000 raw waveform samples into the prompt and asked the model to execute a signal-processing
algorithm mentally. A 7B model replied, not unreasonably:

> *"It looks like you've provided a list of numerical values. Could you please
> clarify what you would like to do with this data?"*

The task was not hard; it was **ill-posed**, and no LLM can do it. Our simulator
had been substituting a plausible number for a question that could not be asked.
We reshaped the task into the code-generation eval reported in §6.2.

We report this because we suspect it is not rare. Simulated or mocked harnesses
are common in benchmark development, and they are structurally incapable of
detecting an ill-posed task: they invent responses to prompts no real model would
engage with. **A benchmark that has never been run against a live model should not
be trusted, including by its authors.** This is an instance of the general
principle the framework exists to defend — that evidence must come from
measurement, not from a plausible-looking artefact.

---

## 7. Limitations

We state these plainly, because the framework's own thesis obliges us to.

- **The suite is an MVP.** Two evaluations, both from one family
  (software-agent), both in seismology. The document-based and research-workflow
  families are specified and implemented in the substrate but not yet populated
  with mature evals.
- **Small N.** 11 and 20 items; 5 models; one run per configuration. The
  qualitative separation between §6.1 and §6.2 is large and mechanistically
  explained, but the individual scores carry meaningful uncertainty and we do not
  report confidence intervals over a single deterministic run.
- **One skill per eval.** Skill lift is a property of the *(model, skill)* pair,
  and a differently-written skill would produce different lifts. We claim that
  lift is the right quantity to measure, not that our particular skills are
  optimal.
- **The 7–8B failure in §6.2 is a floor, not a ceiling.** These models were given
  a single attempt with no tool loop and no error feedback. The claim is that
  *scaffolding of the skill variety* does not rescue them — not that no
  scaffolding can.
- **Cost is marginal token cost.** It excludes electricity, hardware
  amortisation, and the substantial wall-clock cost of local inference, which is
  real and which a laboratory feels.

---

## 8. Roadmap and contribution model

The framework is deliberately separable from the evaluations that populate it.
Additional evaluations, contributed by members of our group, are in preparation —
spanning ambient-noise processing, waveform simulation, and literature synthesis —
and will slot in as entries against the three families of §3.5 without
modification to the substrate.

We adopt an explicit attribution model, which we recommend to others building
federated benchmarks: **framework authorship and eval authorship are recorded
separately.** Each eval carries its own authors, its own versioned skill, and its
own citable dataset; the leaderboard credits eval contributors distinctly from
framework authors. This is what allows a benchmark to grow by community
contribution without either diluting the contributors or absorbing them.

---

## 9. Conclusion

The question a scientific laboratory needs answered is not whether AI is good. It
is *what is the cheapest thing that is good enough here, and am I allowed to run
it on my data.* Answering that requires an evaluation instrument that treats cost
as a first-class axis, that measures the deployed *(model, scaffolding)* pair
rather than the model, that verifies against references rather than judgements,
that penalises confident invention, and whose answers cannot have been trained on.

Our demonstration suggests the answer is not uniform, and that its structure is
usable: **scaffolding substitutes for scale on selection tasks and fails to on
code generation.** We expect the boundary of that rule to be the interesting
object of study, and we have built the instrument to find it.

---

## Author contributions

M.D. conceived the framework, including the frugality-first framing, the
scorability spectrum, negative-case discipline, skill-conditioned evaluation and
the skill-lift quantity, the three-family taxonomy, and the secret-seed
contamination-control design; designed and implemented the evaluation suite and
the live protocol; and wrote the paper.

Contributed evaluations (in preparation, §8) will be credited to their respective
authors under the attribution model described therein.

## Data and code availability

The framework, the public `validation` splits, and the exact figures and data
behind §6 are released with this paper. The hidden `test` splits are available as
a gated dataset; the generator is public and auditable, and only the master seed
is withheld (§3.6). The cost-vs-performance figure and its underlying table are
downloadable as PNG and CSV from the public leaderboard.

---

### Notes for revision (not for submission)

- **Venue.** The audience that matters for this claim reads arXiv + a NeurIPS/ICLR
  AI-for-Science workshop, not a geoscience journal. A geoscience venue (Seismica)
  is the right home for the *evals*, later, not for the framework.
- **Figure 1** should be the cost-vs-performance plane with skill arrows — it
  carries §6.1–6.3 on its own and is already publication-ready (PNG/CSV export).
- **Strengthen before submission**: (a) repeat runs to put error bars on the
  scores; (b) at least one document-based or workflow eval, so the three-family
  taxonomy is demonstrated and not merely proposed; (c) the ReAct/error-feedback
  experiment from §6.3, which would convert a limitation into a second finding.
- Related-work section (§2) currently asserts positioning without citations and
  must be filled in properly.
