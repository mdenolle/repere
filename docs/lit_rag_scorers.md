# Literature / RAG scoring (Family 1): dimensions and metrics

Status: implemented. Reference: `src/frugalmind_suites/lit_rag/`. Corpus:
the real OOI Regional Cabled Array literature that the deployed
[aRCADA](https://github.com/mhemmett/arcada) assistant retrieves over.

## What is being evaluated

aRCADA's literature mode is a retrieval-augmented pipeline: BM25 over paper
abstracts and full-text chunks, top-k context, a model that answers and cites.
Every question a facility might trust it with reduces to a small number of
checks that have a reference answer, so this suite scores those checks with
no LLM in the loop (tier T0 on the scorability spectrum) and leaves rubric
judging as an explicit, opt-in fallback. The paper plan calls this the
*reference-verified* tier: literature retrieval and attribution scored against
a date-bounded corpus.

## The corpus

`data/ooi_rca_corpus.json` — 142 papers (2013–2025) frozen from the Zotero
"OOI RCA" collection by `scripts/build_ooi_rca_corpus.py`. Each document
carries title, abstract, DOI, year, journal, first author and the instruments
aRCADA links it to. The document `id` **is the DOI**, the same key aRCADA's
own index cites (`paper::<doi>`), so gold in this suite refers to what the
deployed system would return. The file records its provenance (source repo,
commit, sha256 of the upstream file, build time); a leaderboard row pins to
that hash.

Nothing in the corpus or the truth set is synthetic. Two upstream metadata
defects are excluded as gold targets (`10.1029/2020gl087372` carries another
paper's abstract; `10.1002/rob.21961` duplicates `10.1029/2020EA001269`) and
11 papers have no usable abstract; all stay in the corpus as distractors.
Publication dates are year-only, so `cutoff_date` compares by year until a
`published` field is added (Crossref enrichment is the obvious source).

## Dimensions

Each dimension is one deterministic scorer, reconstructable from a
serialisable `scorer_spec`, so a row can be scored anywhere.

| Dimension | Question it answers | Scorer | Scalar | Reported alongside |
|---|---|---|---|---|
| **Retrieval** | Did the right paper come back, and how high? | `retrieval_metrics` | MRR (single-shot ranking) or nDCG@5 (agent) | recall@k, precision@k |
| **Attribution** | Are the citations real, are they the right ones, and are the facts there? | `attribution` | ⅓·validity + ⅓·citation recall + ⅓·fact coverage − 0.25·forbidden | `citation_validity`, `citation_precision`, `citation_recall`, `fabricated` (the list), `fact_coverage`, `n_forbidden`, `abstained` |
| **Abstention** | Does it decline exactly when it should? | `abstention` | proper rule (below) | `abstained`, `answerable` |
| **Term preservation** | Do identifiers survive translation verbatim? | `term_preservation` | required present − forbidden present | — |
| **Tool use** (agentic runs) | Could it drive the harness? | `tool_use_stats` | — | `n_tool_calls`, `n_tool_errors`, `submitted`, `converged` |
| **Cost** | What did it cost to get there? | telemetry | USD, tokens | wall clock, epochs |
| **Reliability** | Same answer on a re-run? | Inspect `epochs` | mean ± stderr per task | per-sample variance |

The attribution breakdown rides in `Score.metadata` on every Inspect sample
so a blended scalar never hides a fabricated citation: a run can score 0.83
and still carry `fabricated: ["10.9999/made-up"]` in plain sight.

### Retrieval

Gold is the paper a question was written from (known-item), so relevance is
objective. Candidates shown to the model are **hard distractors**: the corpus
documents with the highest content-word overlap with the gold. Random
distractors made the arXiv suite trivially solvable by keyword matching
(two unrelated models scored 1.0 unskilled), which is the failure mode this
guards against. Display order is a hash, so the gold's slot varies.

### Attribution

Citations are recognised as DOIs anywhere in the answer
(`[10.1126/science.aah5563]`, `doi:10…`, `https://doi.org/10…`) or as
bracketed short keys (`[S2]`). Comparison is case-insensitive.

* *validity* — cited ids that resolve to a provided source. One fabricated
  id out of two cited halves it.
* *citation recall* — gold sources that were cited. A lit-review answer that
  never cites the paper that says the thing is not grounded, however fluent.
* *citation precision* — cited ids that are gold. Reported, not blended:
  citing a provided but irrelevant source is visible without being punished
  twice.
* *fact coverage* — `required_terms` present verbatim. Terms are quoted from
  the gold abstract (a test enforces this), so coverage is objective; the
  cost is that a correct paraphrase ("two months" for "8 weeks") scores 0 on
  that term. Author required terms as numbers, dates and named entities, not
  phrases.
* *forbidden* — wrong numbers or renamed sites a confabulating model tends to
  produce; each costs 0.25.

An uncited answer scores 0 on validity and recall by construction.

### Abstention

A retrieval system that always answers has a false-positive problem the
retrieval metrics cannot see. The suite pairs unanswerable queries (no
relevant paper exists in the corpus; audited by keyword at authoring time,
several deliberately sharing vocabulary with real papers so BM25 returns
plausible hits) with answerable controls drawn from the known-item set. The
model must reply with exactly `NO_RELEVANT_PAPERS` to decline.

Scoring rule:

| | declines | answers |
|---|---|---|
| unanswerable | 1 | 0 |
| answerable | 0 | fraction of gold cited |

Declining is never free and never punished when it is right, so the rule is
proper: the score-maximising policy is to abstain exactly when there is no
relevant evidence. The deployed lexical retriever never abstains; its row on
this suite is the floor.

### Term preservation

Real abstract sentences; identifiers (station codes, coordinates, dates,
numbers with units) must appear verbatim in the translation. Forbidden terms
catch locale reformatting (`1.535` for `1,535`).

## Slicing metadata

Every item carries `site`, `topic`, `difficulty`, `hazard_relevant` and
`answerable`. `hazard_relevant` marks questions whose wrong answer has
operational consequence (eruption forecasting, slow slip, early warning);
the paper reports those separately from aggregate accuracy.

## Baselines

`agent_tasks.py@lexical_retrieval_baseline` runs the deployed retriever alone
(`search_corpus`, top-k, no model) through the same tasks and scorers. Every
agent row is read against it: an agent that does not beat BM25 on retrieval,
or does not abstain where BM25 cannot, has not earned its cost.

## Reliability

All Inspect tasks take `-T epochs=N`; the scorer reports `mean` and `stderr`
per task. Five epochs is the minimum before comparing two rows on the
leaderboard; temperature 0 does not make a tool-using trajectory
deterministic.

## Running

```bash
# single-shot, candidates in the prompt
inspect eval src/frugalmind_suites/lit_rag/inspect_tasks.py@retrieval   --model ollama/qwen2.5:7b
inspect eval src/frugalmind_suites/lit_rag/inspect_tasks.py@abstention  --model ollama/qwen2.5:7b -T epochs=5
inspect eval src/frugalmind_suites/lit_rag/inspect_tasks.py@grounded_qa --model anthropic/claude-haiku-4-5

# agentic: the model must search the corpus itself
inspect eval src/frugalmind_suites/lit_rag/agent_tasks.py@grounded_qa_agent \
    --solver src/frugalmind/agents/solver.py@lit_rag_react --model ollama/qwen2.5:7b

# the deployed retriever, no model
inspect eval src/frugalmind_suites/lit_rag/agent_tasks.py@retrieval_agent \
    --solver src/frugalmind_suites/lit_rag/agent_tasks.py@lexical_retrieval_baseline --model none/none
```

## Truth set and splits

`ooi_rca.yaml` is the public validation split (20 known-item, 8 unanswerable
+ 6 answerable abstention items, 7 + 2 grounded-QA, 2 translation). Ranked
scores come from a hidden test split in the same schema at
`$FM_EVAL_DATA_DIR/lit_rag_ooi_rca_test.yaml`, merged when present and never
committed; requesting `split="test"` without it fails loudly. Authoring
rules, enforced by tests: gold ids exist in the corpus and are not the
defective records; grounded-QA required terms appear verbatim in the gold
abstract; unanswerable items have empty gold; the committed file contains
only `validation`/`public` rows.

To add items from real user requests (the paper's task-provenance
requirement), append to the YAML under the kind that fits and run
`pytest tests/test_lit_rag_scorers.py`.

## Not implemented (by design)

- **Faithfulness judge.** A T4 judge that checks each claim is entailed by a
  retrieved passage, wired like the STA/LTA report judge (opt-in, off in
  CI). Use only where `attribution` cannot express the check, and report
  agreement with human anchors next to any judge score.
- **Full-text chunks.** aRCADA indexes PDF chunks for one paper today;
  the corpus here is abstract-level. When full text lands, `required_terms`
  can be drawn from body text and the same scorers apply.
- **Multimodal input.** Figure/waveform questions need vision plumbing in
  `adapters.py` first; the answer still scores through the scorers above.
