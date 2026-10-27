# RCA Atlas: owned upstream, evaluated in Repère

Decision (Marine Denolle, 2026-10-15): **RCA Atlas owns the RCA golden items.
Repère implements the evaluation and displays the results.** This replaces the
earlier version of this page, which proposed exporting Atlas cases into
Repère's `datasets/`. That would have kept two copies of every case, and the
Atlas licence does not allow it.

Everything below was read from `coszo-hub/RCA-Atlas` at `e8d828d` (2026-10-14)
and checked against Repère `main`. What is implemented is marked; the rest is a
plan.

## 1. The licence decides the mechanism

RCA Atlas is a public GitHub repository under the "RCA Atlas Proprietary
License": authorised project members may use the materials for authorised
project work, and nothing may be copied, redistributed or published without
written permission from the copyright holder. Repère is a public repository,
a PyPI package and a public board. So:

| Repère may | Repère may not |
|---|---|
| download Atlas files at run time into `$REPERE_EVAL_DATA_DIR` (gitignored, outside the wheel) | commit or package an Atlas row, prompt or gold value |
| commit the commit SHA and each file's SHA-256 | quote Atlas cases in its docs or site |
| publish aggregate scores, if the Atlas owners agree (open question 1) | publish per-item outputs that reproduce Atlas content |

`src/repere/publish.py` already refuses free text on the board, which covers
the last row.

## 2. Pulling (implemented)

| Piece | File |
|---|---|
| Commit and per-file SHA-256 for 11 datasets | `src/repere_suites/atlas/pins.yaml` |
| Verified download and loader | `src/repere_suites/atlas/__init__.py` (`fetch_atlas`, `load_atlas`) |
| Command | `pixi run python scripts/pull_atlas.py [--check]` |
| Tests, no network | `tests/test_atlas_pull.py`, including a guard that no pinned file is committed |

A file whose hash differs from its pin is refused and not written, so a moved
branch or an edited case cannot be scored silently. To take a new Atlas
release, change `commit`, recompute the hashes, and record the change in
`CHANGELOG.md`; scores before and after are on different dataset versions.

The routing pin equals the `dataset_sha256` that Atlas's own runner recorded in
`results/2026-10-08-baseline/provenance/routing.json`, so the two harnesses name
the same file the same way.

**The pin is provisional.** `e8d828d` is on Atlas's unmerged
`rca-atlas-eval-suite` branch, which has since moved two commits. Repin to a
release tag on Atlas `main` (open question 2).

## 3. What Repère can evaluate with its own models

Atlas has eleven suites. Only four put a language model in the loop; the rest
test Atlas's own NumPy tools or its retriever.

| Atlas dataset | Rows | Atlas tests | In Repère |
|---|---|---|---|
| `agent_tasks` | 21 | an LLM agent calling the 11 `atlas_tasks` tools over MCP | **First target.** The model chooses tools and reports `{"answer": ...}` |
| `routing` | 156 (83 dev, 73 test) | a rule-based router and the Worker's JavaScript | a 15-class classification prompt, scored by exact match |
| `quake_questions` | 26 | the Worker's date parser | extraction of `{start, end, min_mag}` given `now_utc` |
| `rca_eval` + `rca_eval_gold` + `answers_extra` | 60 + 60 + 12 | Gemini and Groq answering over retrieved evidence | needs Atlas's frozen evidence packages (`model_eval.runner.run_frozen_answer_eval`); the corpus is not in the datasets |
| `gaps`, `timing`, `dvv`, `pressure`, `quakes` | 120, 60, 72, 72, 35 | the tools, called directly | not a model evaluation as they stand; they become one only as code-writing tasks |

None of these is held out from Repère's point of view: every row, including
routing's `test` half, is in a public repository. Under
[`../holdout_policy.md`](../holdout_policy.md) they give public-set numbers.
Held-out cases need fresh draws from Atlas's seeded generator
(`src/atlas_eval/synth.py`) with a secret seed that never enters either
repository. That works for `agent_tasks` and the synthetic suites, not for the
hand-labelled ones.

## 4. Skill lift on the agent tasks

What the Atlas agent receives today (`src/atlas_eval/suites/agent.py`):

| Element | Content |
|---|---|
| System prompt | two sentences appended to Claude Code's: work only through the atlas MCP tools, do not ask questions |
| Tool descriptions | `TOOL_SCHEMAS` in `src/atlas_tasks/tools.py`, one sentence per tool; only the two pressure tools say which to use when |
| Harness | `claude -p --model haiku`, at most 12 turns, all non-Atlas tools disallowed |
| Not given to the agent | the conventions in `src/atlas_tasks/README.md`: sign of Δt, dv/v as a fraction while tasks ask for percent, UTC days, `missing_days` |

There is no SKILL.md, AGENTS.md or prompt file. The one before/after Atlas
recorded is sharper tool descriptions (Haiku 18/20 to 21/21, then 20/21 on a
rerun), one model and one run each, so it is not a skill-lift measurement.
Running under Claude Code also mixes Claude Code's own system prompt into the
condition.

Plan for Repère, same 21 tasks, every model in `config/models.yaml`, K=5
repeats:

| Condition | Agent gets | Isolates |
|---|---|---|
| `code-only` | `python_session`, no Atlas tools | baseline |
| `tools-only` | Atlas MCP tools and Atlas's two-sentence prompt | tool lift (vs `code-only`) |
| `tools+skill` | as above plus a SKILL.md on the tool conventions | skill lift (vs `tools-only`) |

The SKILL.md describes Atlas's tools, so it should be authored in RCA Atlas
and pulled at the same pin as the data. With n = 21, Atlas's own method note
(§4) gives a 95 % half-width near ±20 points at 50 %; only large lifts will
show. Growing the task set from the generator fixes that and gives the held-out
draw at the same time.

Repère has no MCP client yet (`src/repere/agents/react.py` wires three local
tools). Two routes: Inspect's stdio MCP tool support, if the pinned
`inspect_ai` version has it (not checked: Inspect is not installed in either
local pixi environment), or a small tool-calling loop over
`OpenAICompatAdapter`, which already reaches Ollama.

## 5. Display (not started)

Repère's board shows scores per suite, condition and model, with the cost
frontier. For the Atlas suites that means aggregates only, labelled with the
Atlas commit and file hash. Showing the items themselves on Repère's public
site would be public display of Atlas material; link to Atlas's own catalog
instead, unless the owners grant permission.

## 6. Overlap with Repère's own RCA seeds

| Repère | Atlas | Plan |
|---|---|---|
| `rca-coding-timing-offset-hys14-001`, `-resyncs-002` (real HYS14 against chronfix, V1) | `timing_v1` (synthetic); `EVALUATION_METHOD.md` §10.1 plans the real HYS14 set | migrate to Atlas as the start of §10.1 |
| `rca-coding-qc-continuity-001` (real data) | `gaps_v1` (synthetic) | migrate; complementary |
| codameter dv/v suite | `dvv_v1` (synthetic) | keep one generator; decide which |
| 5 `rca-sensor-*`, 5 `rca-litreview-*` (templates) | `rca_eval_v1` (60 questions, 14 categories, `corpus_verified` gold) | retire in favour of Atlas's set |

## 7. Questions for the RCA Atlas owners

1. May Repère publish aggregate scores computed on Atlas data on its public
   board? The licence requires written permission for publication.
2. Will Atlas tag a dataset release on `main` for Repère to pin?
3. Where do held-out RCA items live? Atlas has no private partition; a gated
   store (for example a gated Hugging Face dataset owned by the project) is the
   pattern Repère uses.
4. Will Atlas rows gain a review trail (author, verifier, source reference),
   as `rca.golden.v0.1` records have?
5. Atlas's published `catalog.html` embeds gold for routing `test` rows,
   retrieval and answers. That is Atlas's choice, but it means those rows can
   never be held out.

## 8. Order of work

| Step | Where | Status |
|---|---|---|
| Pull at a pinned commit with hash checks | Repère | done |
| Remove Atlas rows from Repère; guard against recommitting | Repère | done |
| Tag a dataset release; answer §7 | Atlas | open |
| Atlas agent suite in Repère: MCP tools, scorer reproducing `AgentSuite.score_case`, three conditions | Repère | next |
| SKILL.md for the Atlas tools | Atlas | open |
| Routing and quake_questions as model suites | Repère | after the agent suite |
| Board display of Atlas aggregates | Repère | after question 1 |
| Migrate the overlapping RCA seeds | Atlas | open |
