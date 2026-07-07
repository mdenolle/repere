# Literature / RAG / multimodal scoring (Family 1)

Status: proposed (Phase 4 candidate). Reference implementation:
`src/frugalmind_suites/lit_rag/`.

## Why

Literature tasks (review, critique, translation, RAG question-answering,
figure interpretation) look "open-ended" and tempt you toward one T4 LLM-judge
blob. That is noisy and expensive. The verifiable-core stance: **decompose each
task into the piece that has a reference gold**, and score that with no LLM in
the loop. The judge becomes an opt-in fallback, not the primary signal.

## Decomposition

| Sub-task | Verifiable core | Scorer | Tier |
|----------|-----------------|--------|------|
| RAG retrieval | ranked docs vs gold relevant set | `retrieval_metrics` | T0 |
| Translation | domain terms must survive verbatim | `term_preservation` | T0 |
| Grounded QA | citations resolve to real sources; facts present | `citation_support` | T0 |
| Interpolation | held-out text/value predicted | reuse `numerical_regression` / lexical | T0–T1 |
| Review / critique | rubric criteria | pinned-rubric LLM-judge (P3.5) | T4 |
| Multimodal | answer about a figure/waveform | any of the above on the answer | T0–T4 |

The three scorers shipped here are the T0 core. Review/critique reuses the
STA/LTA `report` scorer's judge-fallback pattern (lexical first, `max(lexical,
judge)`) and the `pre-submission-reviewer` skill's rubric — not duplicated here.

## Scorers (all deterministic, pure Python)

### `retrieval_metrics`
`gold` = list of relevant document ids; model returns a ranked JSON array.
Metrics: `recall_at_k`, `precision_at_k`, `mrr`, `ndcg_at_k` (binary-gain,
ideal-DCG normalised). Report retrieval **separately** from answer quality — a
good answer over bad retrieval is luck, not grounding.

### `term_preservation`
Translation must preserve identifiers exactly (station codes `NC.JBGB`,
magnitudes `M4.2`, phases `Pn`). Score = fraction of `required_terms` present −
penalty per `forbidden_terms` hit (e.g. a rounded magnitude `M4.0`, a renamed
phase `Pg`). Case-sensitive by default so `HHZ` ≠ `hhz`.

### `citation_support`
The RAG hallucination guard, and the negative-case discipline generalised.
Answer must cite inline `[S#]`; score = 0.5·(fraction of citations that resolve
to a **provided** source) + 0.5·(fraction of required facts present) − penalty
for forbidden tokens (e.g. a fabricated `[S9]`). No citations → 0 on the
validity half.

## Serialisable spec

Each `tasks.yaml` row carries its own `scorer: {name, config}`; the generic
Inspect `lit_rag_scorer` reconstructs it from `sample.metadata['scorer_spec']`.

## Not in this reference (design only)

- **Multimodal input.** `Sample.input` must carry `ContentImage` (waveform
  figures, station maps, spectrograms) and `adapters.py` must forward images to
  vision models. This is the one genuine substrate change Family 1 needs; the
  *answer* still scores via the T0–T4 scorers above. Add to `adapters.py` before
  authoring multimodal tasks.
- **Faithfulness LLM-judge.** A judge that checks each claim is entailed by a
  retrieved passage, wired like the STA/LTA report judge (opt-in, off in CI).
  Use it only where `citation_support` can't express the check.
- **Judge reliability.** When a rubric judge is used, score it against a few
  human-labelled anchors and report agreement, so the leaderboard shows judge
  reliability rather than treating judge output as ground truth.
