# Authoring golden records for FrugalMind-RCA

This is the contract for co-authors. The validator
(`python -m frugalmind_suites.rca.validate`) enforces everything marked with a
rule id; the rest is judgement, and the reviewer checks it.

## 1. Lifecycle

| status | Meaning | Who sets it |
|---|---|---|
| `template` | written by an assistant as a skeleton; nothing in it is ground truth; must carry at least one TODO (R10) | the assistant, never a person |
| `draft` | a named person is writing it; TODOs allowed | the author |
| `verified` | a second named person checked the gold against the source, ran the oracle or self-test, and recorded how in `provenance.verification`; zero TODOs (R10) | the verifier, not the author |
| `frozen` | included in a released suite version; image digest pinned for shape B (R10); never edited again, only retired | the release owner |
| `retired` | superseded or found wrong; file kept, id never reused | the release owner |

A record moves `template -> draft` the moment a person edits it: replace
`provenance.author: assistant-template` with your name and role. `--strict`
validation (used for release builds) fails on any template.

## 2. What every record needs

1. **A prompt a real user would write.** No instrument ids or channel codes
   unless a real user would know them; resolving them is usually the task.
   Never put the answer, the checker logic or a corpus id in the prompt (R12).
2. **Provenance you can open.** `source` says where the fact comes from;
   `source_ref` pins it (commit hash, DOI, query URL with date). "Personal
   expertise" is allowed for T4 rubrics only, and then `author_role` matters.
3. **A holdout construction** (R09 for catalog-derived items). Ask: "could a
   script that string-matches the aRCADA catalog or paper index answer this?"
   If yes, change the item or use `catalog_excluded`. `paraphrase_only` is
   never allowed on the test split (R08).
4. **A cutoff date and corpus snapshot** for anything with a retrieval surface
   (R05 for T3). Use the snapshot's commit date unless you have a reason.
5. **TODOs that are questions**, not notes. "Confirm HHZ is archived at
   EarthScope for HYS14" is a TODO; "check things" is not.

## 3. Per-tier rules

### T1 physics-verified (`oracle_compare`)

- `scoring.oracle.solver` is an importable function under
  `frugalmind_suites.rca.oracles`; the reference is computed at scoring time,
  never typed into the record.
- `independent_measurement` must say what the reference is *and what it is
  not*. For chronfix it is a software estimate validated closed-loop against
  HYS12 (DESIGN.md §3.1c); say so.
- `tolerance` (R03) must be justified from the reference's stated precision
  and written in units. Placeholder tolerances are TODOs.
- Provide a self-test solution under `seeds/<family>/_selftest/good/<id>.md`
  that lands inside the tolerance; if it does not, the tolerance or the task
  is wrong (ABC T.8, T.9).
- Public T1 items must not be answerable by looking up the public reference
  file; put items whose reference is public on the validation split and keep
  test items on windows the public reference does not cover.

### T2 execution-verified (`execution_check`)

- Shape B only (R04). List `task.artifact_keys` the code must `record(...)`.
- `scoring.checker` names a function in `frugalmind_suites.rca.checkers`;
  `args.expected` holds the reference values; use `all_or_nothing: true`
  for negative-case controls.
- Every T2 record ships a known-good and a known-bad self-test answer under
  `_selftest/good/` and `_selftest/bad/`; the harness self-test must give
  them 1.0 and at most the code+runs stages (0.3 by default).
- `sandbox.network`: `none` when inputs are files; `replay` with a cassette
  when the script must fetch; `allowlist` only for record-mode runs.
- Pin every input file by sha256 (R13). Files under `data/public/` are
  committed; large or licensed inputs go through
  `scripts/rca_fetch_external.py` with a pinned hash, or to the private root.
- Author the positive and the negative case together (a window with a gap and
  a clean window; a triggering window and a quiet one).

### T3 reference-verified (`retrieval_metrics`, `citation_support`, `exact_match`)

- `reference_citations` carries graded relevance 0 to 3. Grade 0 entries are
  deliberate negatives (papers the corpus links by keyword but that do not
  qualify); include some.
- For `citation_support`, `required_terms` must be facts from paper bodies or
  synthesis, not phrases from one abstract.
- Abstention items (`exact_match` with `mode: abstain`) are required in every
  batch: the agent must be able to say "nothing before the cutoff".
- Record who graded, when, and whether a second grader agreed (kappa) in
  `provenance.verification.method`.

### T4 judgment-dependent (`rubric_judge`)

- `rubric_ref` points to a pinned rubric under `docs/rca/rubrics/` with binary
  criteria.
- `min_raters >= 2` (R06). No judge score is reportable until two humans have
  rated the calibration set, the agreement statistic clears the threshold, and
  the judge's agreement with the humans is published; the scorer voids T4
  items until then.
- Photos: every image needs `source_url`, `license`, `attribution`,
  `permission_status` (R14). Nothing is scraped.

## 4. Facts you must not invent

Instrument specifications, channel codes, deployment dates, stream names,
DOIs, award numbers, prices. If you cannot open a source for it, leave a TODO
with the exact question. Placeholder DOIs (`10.0000/...`) are rejected (R11).

## 5. Review checklist (the verifier fills this in `provenance.verification.method`)

- [ ] I opened `source_ref` and the fact is there.
- [ ] I ran the self-test (T1, T2) or re-graded a sample (T3) or rated the
      calibration set (T4), on this date.
- [ ] The BM25-only baseline does not answer this item (`run.py --solver`
      with `baselines.bm25_only`, see DESIGN.md §3.4).
- [ ] The prompt does not leak the answer.
- [ ] Licence and attribution are stated for every input file and photo.
- [ ] Zero TODOs remain; status set to `verified`.

## 6. Commands

```bash
python -m frugalmind_suites.rca.validate                 # all seeds
python -m frugalmind_suites.rca.validate --strict         # release build
python scripts/rca_fetch_external.py                      # pinned inputs
python -m frugalmind_suites.rca.run --ids <id> \
   --solver scripted:src/frugalmind_suites/rca/seeds/coding/_selftest/good \
   --model mockllm/model --epochs 1 --out results/rca    # self-test
```
