# Evaluating open models as tool-using data/RAG agents

This is the guide for evaluating **coding and retrieval agents** in Repère
— including open-weight models served locally (Gemma, Qwen, Mistral, …)
alongside frontier API models. It covers *why* we attach tools to the base
models, the harness that keeps the comparison fair, the two-axis scoring model,
and copy-paste recipes for **adding a tool** and **adding an agentic task**.
The literature-RAG suite is the worked example.

Related docs: [`telemetry.md`](telemetry.md) (the log schema the metrics land
in), [`lit_rag_scorers.md`](lit_rag_scorers.md) (the deterministic scorers).

---

## 1. Why attach tools at all

For a suite that measures **data processing** or **retrieval**, the thing under
test is not "does the model know the answer" — it's "can the model *use tools*
to produce a correct artifact from real data / a real corpus." A bare
completion from `gemma` or `qwen` can only *describe* an STA/LTA detector or
*guess* at citations; it can't run code on a miniSEED trace or retrieve from a
frozen paper corpus. Evaluating the raw model with no tools therefore measures
recall of recipes, not agentic competence — a much weaker benchmark for
Repère's cost-routing thesis.

So the canonical eval path is a **tool-using ReAct agent**, not single-shot
`generate`. The model calls tools, inspects results, and submits an artifact
that a **deterministic scorer** checks — the detected picks, the dv/v series,
or a ranked list of document ids — never the prose.

## 2. The one rule that makes open-vs-frontier fair

> **Hold the tool surface and the agent scaffold constant. Vary only the model.**

If `gemma` gets a different tool contract than Claude, you're benchmarking two
harnesses, not two models. Two pieces enforce this:

- **A tool *registry*** ([`agents/registry.py`](../src/repere/agents/registry.py))
  — tools are registered once under stable names; every suite requests them
  *by name*, so the exact same tool objects attach to every model.
- **A generic ReAct *solver*** (`frugal_react` in
  [`agents/solver.py`](../src/repere/agents/solver.py)) — one scaffold
  (ReAct loop, submit mechanics, message cap) parametrised by a tool-name list
  and a system prompt. `stalta_react` and `lit_rag_react` are thin
  specialisations; every suite and model runs through the same code.

The only thing that changes between `ollama/qwen2.5:7b` and
`anthropic/claude-haiku-4-5` is the `--model` flag.

## 3. Running an open model

Open-weight models reach the identical harness through any OpenAI-compatible
endpoint (Ollama, vLLM, LM Studio). Inspect addresses them with a provider
prefix:

```bash
# Local Ollama, literature-RAG agent:
inspect eval src/repere_suites/lit_rag/agent_tasks.py@retrieval_agent \
    --solver src/repere/agents/solver.py@lit_rag_react \
    --model ollama/qwen2.5:7b

# vLLM / any OpenAI-compatible server:
inspect eval src/repere_suites/sta_lta/inspect_tasks.py@trigger_code \
    --solver src/repere/agents/solver.py@stalta_react \
    --model openai/Qwen2.5-7B-Instruct -M base_url=http://localhost:8000/v1

# Frontier baseline — same task + solver, only the model changes:
inspect eval src/repere_suites/lit_rag/agent_tasks.py@retrieval_agent \
    --solver src/repere/agents/solver.py@lit_rag_react \
    --model anthropic/claude-haiku-4-5-20251001
```

The `[eval]` extra is required (`pip install -e ".[eval]"`); the registry,
metrics, and literature modules import `inspect_ai` lazily so the rest of the
package stays importable without it.

## 4. Score two axes, not one

Tool-attachment introduces a second failure mode that must be measured
*separately* from task correctness:

| Axis | Question | Where it comes from |
|------|----------|---------------------|
| **1. Task correctness** | Given it ran, is the artifact right? | the suite's deterministic scorer (`stalta_scorer`, `lit_rag_scorer`) |
| **2. Tool-use competence** | Could it drive the harness — valid calls, convergence, a submit? | `tool_use_stats()` in [`metrics.py`](../src/repere/agents/metrics.py) |

A small model that scores 0 because it **never emitted a valid
`record_submit`** is failing differently from one that submitted a **wrong
answer**. Collapse them and the router can't tell "too dumb for the task" from
"can't work the tools." Keep them apart.

Wire it in with the drop-in wrapper — axis 1 (`value`) is untouched, axis 2
rides along in `Score.metadata['tool_use']`:

```python
from repere.agents.metrics import with_tool_metrics
Task(dataset=..., scorer=with_tool_metrics(lit_rag_scorer()))
```

A telemetry sink then lifts it into the sample's `extra` field so both axes sit
side by side in the JSONL log.

## 5. Retrieval: use a **corpus tool**, not `web_search`

For literature retrieval the reflex is "add a `web_search` tool." **Don't** —
not for the reproducible benchmark. The lit_rag retrieval scorer grades a
ranked list of document ids against a gold set with nDCG
([`lit_rag_scorers.md`](lit_rag_scorers.md)), which only works over a **frozen,
versioned corpus with stable ids**. Live web search breaks it three ways:

- **Non-deterministic** — results shift daily, so nDCG-against-gold becomes
  unrepeatable; the whole framework leans on deterministic scoring.
- **Un-date-boundable** — [`ROADMAP.md`](../ROADMAP.md) makes `cutoff_date` a
  hard contract (a retrieval agent must not query past the cutoff). Web search
  can't enforce it and will leak post-cutoff papers.
- **Wrong return shape** — the scorer parses stable ids (`[S1]`, `OOI-003`),
  not live URLs.

Instead, `literature_search` ([`agents/lit_tools.py`](../src/repere/agents/lit_tools.py))
retrieves over a snapshotted corpus with the cutoff enforced **inside the
tool** — the agent physically cannot surface post-cutoff work. The pure,
deterministic, offline core is in
[`agents/literature.py`](../src/repere/agents/literature.py); the corpus is
[`lit_rag/data/ooi_corpus.json`](../src/repere_suites/lit_rag/data/ooi_corpus.json).

> **The seed corpus is a placeholder.** Its abstracts are synthetic and its
> DOIs are non-resolvable (`10.0000/ooi-seed-*`). Replace `documents` with the
> group's real OOI/COZI papers — schema, ids, tooling, and gold sets stay the
> same. Point at a different file with `FM_LITRAG_CORPUS=/path/to/corpus.json`.

Retrieval gets a third, domain-specific harness signal beyond §4:
`retrieval_leakage(submitted_ids, corpus, cutoff_date)` returns any **fabricated**
ids (not in the corpus — a hallucinated citation) and **leaked** ids (published
after the cutoff). In a correct run both are empty.

When *would* `web_search` be legitimate? Only for an explicit open-web task
scored differently (grounded-QA `citation_support`, checking the answer is
supported by whatever it cited), and even then snapshot the results for replay.
Register it as a separate `web_search` tool with its own toolset — don't let it
substitute for corpus retrieval in the nDCG task.

## 6. Recipe — add a new tool

Three steps, all in [`src/repere/agents/`](../src/repere/agents/):

**Step 1 — write the tool** as an Inspect `@tool` factory. Tools must be
*stateless* and *never raise* — return failures as JSON strings so the agent
can react:

```python
from inspect_ai.tool import Tool, tool

@tool
def spectrogram() -> Tool:
    async def execute(waveform_id: str, nperseg: int = 256) -> str:
        try:
            ...  # keep heavy I/O off the event loop with asyncio.to_thread
            return json.dumps({"ok": True, "png_path": path})
        except Exception as exc:
            return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    return execute
```

**Step 2 — register it** under a stable name (this is where "attach a tool to
every model" happens):

```python
from repere.agents.registry import register_tool

@register_tool("spectrogram", "Compute a spectrogram PNG for a fetched waveform")
@tool
def spectrogram() -> Tool:
    ...
```

For a built-in that should be discoverable without importing its module, add a
lazy `ToolSpec` to `_register_builtin_tools()` in `registry.py` (see how
`literature_search` is wired).

**Step 3 — request it** from any suite by adding its name to the tool list
(§7). Nothing else changes; the solver resolves a fresh bundle per run.

Guidelines: return JSON with an `ok` flag; cap large stdout; run blocking I/O
in `asyncio.to_thread`; mark heavy optional deps with `requires=(...)`.

## 7. Recipe — add a new agentic task/suite

You do **not** write a new solver. Reuse `frugal_react` (or a specialisation)
with the tool names your suite needs.

```python
from inspect_ai import Task, task
from repere.agents.metrics import with_tool_metrics

@task
def retrieval_agent() -> Task:
    # Solver passed on the CLI (--solver …@lit_rag_react) so one task runs
    # across models on an identical tool surface.
    return Task(dataset=_dataset(), scorer=with_tool_metrics(lit_rag_scorer()))
```

For a bespoke tool bundle, build the solver directly:

```python
from repere.agents.solver import frugal_react

solver = frugal_react(
    tool_names=["python_session", "spectrogram", "record_submit"],
    system_prompt=_SYSTEM,
    message_limit=32,   # raise for longer workflows
    max_attempts=2,     # give noisy small models a second submit
)
```

Keep the terminal tool named `record_submit` unless you have a reason not to —
scorers read `state.output.completion`, which `basic_agent` fills from the
submit tool's argument.

## 8. Cost controls

`frugal_react` exposes the two knobs that turn "it eventually got there" into a
measurable cost signal — small models take more ReAct turns, and that shows up
as spend, not a hidden win:

- **`message_limit`** — hard cap on the agent's message budget; also kills
  runaway tool loops. Default 24.
- **`max_attempts`** — submissions allowed before the eval gives up. AstaBench
  uses 1; raise for noisier open models.

Pair these with `BudgetGuard` and the per-token costs in
[`config/models.yaml`](../config/models.yaml) for the cost-vs-quality Pareto
view on the leaderboard.

---

### File map

| File | Role |
|------|------|
| [`agents/registry.py`](../src/repere/agents/registry.py) | Tool registry — register/resolve tools by name. **Add tools here.** |
| [`agents/tools.py`](../src/repere/agents/tools.py) | Built-in STA/LTA `@tool` implementations. |
| [`agents/lit_tools.py`](../src/repere/agents/lit_tools.py) | `literature_search` `@tool` (corpus RAG). |
| [`agents/literature.py`](../src/repere/agents/literature.py) | Pure corpus loader + cutoff-aware ranker + leakage audit (no `inspect_ai`). |
| [`agents/solver.py`](../src/repere/agents/solver.py) | `frugal_react` (generic) + `stalta_react` / `lit_rag_react`. **Add tasks via these.** |
| [`agents/metrics.py`](../src/repere/agents/metrics.py) | `tool_use_stats` + `with_tool_metrics` — axis-2 (harness-competence). |
| [`agents/react.py`](../src/repere/agents/react.py) | Legacy STA/LTA solver entry point (kept for existing `--solver …@stalta_react` runs). |
