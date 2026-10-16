# Packaging a golden data set for Repère

How a golden set goes from "cases I wrote" to a pinned, versioned artifact a
leaderboard row can cite. This page collects what is already spread across
`datasets/README.md`, `docs/dataset_submission.md`, `docs/golden_data_provisioning.md`
and `docs/holdout_policy.md`. Where those four disagree with the code, the code
wins and this page says which.

Checked against `repere` at commit `77a4511` (v0.5.2). The example in
`example/` was produced by running `repere.export.export_suites`, not typed by
hand.

## 0. Three formats exist; use the first for new work

| Format | Schema id | Where it appears | Use it for |
|---|---|---|---|
| **BenchmarkRow JSONL** | `repere.suite.v1` | `datasets/<dataset>/<version>/<suite>.jsonl` + `manifest.json` | Every new suite. This is the release artifact. |
| RCA golden record YAML | `rca.golden.v0.1` | `src/repere_suites/rca/seeds/<family>/*.yaml` | Hand-authored, tool-using items with provenance and a review lifecycle (template, draft, verified, frozen, retired). Not exported to JSONL today (`rca/` has no `export_rows`). |
| Suite fixture JSON | `0.3` | `tests/fixtures/sta_lta.*.validation.json` | Test fixtures only. Same prompts and gold, wrapped as `{items: [...]}`. Not a release format. |

Everything below is about the first row. Section 7 says when an RCA record is
the right authoring surface in front of it.

## 1. The row

One JSON object per line, one `(prompt, gold)` pair per object. Machine-readable
schemas: [`schema/benchmark_row.schema.json`](schema/benchmark_row.schema.json),
[`schema/manifest.schema.json`](schema/manifest.schema.json). The source of truth is the
`BenchmarkRow` dataclass in `src/repere/export.py`.

| Field | Type | Rule |
|---|---|---|
| `id` | string | `dataset_id/suite_id/item_id`, globally unique |
| `dataset_id` | string | directory under `datasets/` |
| `suite_id` | string | JSONL file stem |
| `version` | string | `vMAJOR.MINOR`; bump on any prompt or gold change |
| `task_kind` | enum | `extraction`, `code_generation`, `plotting`, `report_drafting`, `numerical_regression`, `retrieval`, `translation`, `grounded_qa`, `orchestration` |
| `split` | enum | `validation` or `test` |
| `visibility` | enum | `public` or `private`; `test` implies `private` |
| `prompt` | string | what the model sees; never the answer, the checker, or a corpus id |
| `gold` | any JSON | shape set by the scorer |
| `scorer_spec` | `{name, config}` | declarative; resolved by the suite family's `make_scorer_from_spec` |
| `metadata` | object | use `difficulty`, `cutoff_date`, `category`, `source_case` so the leaderboard can slice |

Example (from [`example/`](example/datasets/atlas/v0.1/routing.jsonl), a real
public Atlas routing case; the `exact_match` scorer is a proposal, see the note
under the example):

```json
{"id": "atlas/routing/route-001", "dataset_id": "atlas", "suite_id": "routing", "version": "v0.1", "task_kind": "orchestration", "split": "validation", "visibility": "public", "prompt": "How many Axial earthquakes occurred yesterday?", "gold": {"task": "earthquake_count"}, "scorer_spec": {"name": "exact_match", "config": {"field": "task", "normalize": "lower"}}, "metadata": {"difficulty": "easy", "cutoff_date": null, "source_case": "route-001"}}
```

Manifest, one per `datasets/<dataset>/<version>/`:

```json
{
  "schema_version": "repere.suite.v1",
  "dataset_id": "atlas",
  "version": "v0.1",
  "generated_at": "2026-10-16T00:50:02Z",
  "files": [
    {"dataset_id": "atlas", "suite_id": "routing", "version": "v0.1",
     "task_kind": "orchestration", "path": "atlas/v0.1/routing.jsonl",
     "rows": 2, "sha256": "2f37f8662f8f6c9394143a099a39ea6819f57426b6584916ddd4ceb3b61b74fa"}
  ]
}
```

Note: the manifest records `generated_at`, so regenerating it changes the file
even when no row changed. The `sha256` in `files[]` is the value to pin, not the
hash of `manifest.json`.

## 2. Decide where the hidden gold lives (before writing a row)

Decision rule from `golden_data_provisioning.md`:

| Gold is | Mode | Held as |
|---|---|---|
| a pure function of code plus a secret, cheap to regenerate (minutes) | **A, derive** | one repo secret (the seed); nothing stored |
| real recordings, catalogs, human labels, third-party corpora, or expensive to regenerate | **B, host** | gated Hugging Face dataset, pinned to a commit SHA |

Then the split rule, from `holdout_policy.md`:

> A row that a ranked score is computed from never exists inside `src/`, at any
> commit, in any branch.

`validation` rows are public and may be committed. `test` rows are written
straight into `$REPERE_EVAL_DATA_DIR` (default `<repo>/data/private/`,
gitignored) and never into the working tree, even temporarily. A committed and
later removed test row is compromised: `git log -S` recovers it.

## 3. Procedure

1. **Truth set.** For validation rows, a YAML under `src/repere_suites/<suite>/`
   with `split` and `visibility` on every item. Same top-level shape for the
   held-out file (`events:` / `tasks:` / `cases:`).
2. **Held-out rows.** Author into `$REPERE_EVAL_DATA_DIR/<suite>_test.yaml`.
   Mode A suites: write the generator, keep the seed in `SECRET_SEED` or the
   repo secret, never in git.
3. **Scorer.** Register the factory in the suite's `make_scorer_from_spec`. Go as
   high on the scorability ladder as the task allows (T0 deterministic, T1
   numerical, T2 perceptual, T3 trajectory, T4 rubric). Reuse an existing
   scorer before writing one.
4. **Suite class.** `DenolleGroupSuite` subclass with class attributes
   `dataset_id`, `suite_id`, `version`, `task_kind`, and one `_compose(item)`
   feeding both `items()` (runtime) and `export_rows()` (curation).
5. **Loader contract** (copy `sta_lta/items.py`): `HIDDEN_PATH` honours
   `REPERE_EVAL_DATA_DIR`; merge the hidden file only when reading the packaged
   file; one shared validator for both partitions; the same id in both
   partitions is an error; `split="test"` with no rows raises `FileNotFoundError`
   naming the path.
6. **Provenance without answers.** `provenance.yaml` says where the partition
   lives, how it is distributed, and the contamination risk. No expected values.
7. **Export.**

   ```bash
   pixi run export-suite --suite atlas.routing --visibility public --out datasets/
   ```

   This writes `datasets/atlas/<version>/routing.jsonl` and
   `manifest.json`. Commit both. The exporter's `--visibility public` filter
   is what keeps test rows out of the committed JSONL; check the row count in
   the manifest against your validation count.
8. **Upload** the private partition to the gated HF dataset, then record the
   commit SHA you uploaded.
9. **Tests.** `pytest`, then `REPERE_EVAL_DATA_DIR=/tmp/no-private pytest` (the
   fresh-clone view). `tests/test_no_holdout_in_repo.py` fails if any committed
   truth set has a `split: test` or `visibility: private` row.

## 4. Per-row requirements that are easy to skip

- **`cutoff_date`** on anything with a retrieval surface. A correct answer
  found with post-cutoff knowledge is a leak.
- **Negative cases.** A window with no event, a series with no fault, a
  question whose answer is "nothing before the cutoff". Keep at least one per
  batch on the public split so contributors meet them.
- **`difficulty`** in `metadata`, so scores can be sliced.
- **Observables-only view.** The model never sees `gold`, nor generator
  parameters that determine it. In Mode A the generator's truth keys stay on the
  scorer side (codameter: `golden.observed()` vs `generate()`).
- **No credential in the sandbox.** The seed and the HF token belong to the
  scorer process.
- **Canary string** in the hidden set's documentation, to detect scraping into a
  training corpus.

## 5. Pinning, what goes on a leaderboard row

| Mode | Pin |
|---|---|
| A | package version plus the SHA-256 of the generated `cases.json` (publishable without publishing contents) |
| B | HF commit SHA of the gated dataset plus the `sha256` from `manifest.json` |
| both | `version`, `task_kind`, and the scorer name |

Do not cache a generated hidden corpus or a downloaded gold directory in CI.

## 6. Pre-merge checklist

- [ ] No `split: test` or `visibility: private` row in `src/` or `datasets/`.
- [ ] Held-out rows authored in `$REPERE_EVAL_DATA_DIR`, not committed then removed.
- [ ] Every `scorer_spec.name` resolves in `make_scorer_from_spec` (round-trip test).
- [ ] `id`s unique and prefixed `dataset_id/suite_id/`.
- [ ] `manifest.json` regenerated; `rows` equals the validation count.
- [ ] `cutoff_date` set where retrieval is possible.
- [ ] A negative case is in the public split.
- [ ] Both `pytest` and `REPERE_EVAL_DATA_DIR=/tmp/no-private pytest` pass.
- [ ] Private partition is in the gated dataset, with the SHA recorded.
- [ ] If `package-data` gained a pattern: build the wheel and inspect it.

## 7. When to use an RCA golden record instead

Use `rca.golden.v0.1` YAML (`docs/rca/AUTHORING.md`) when the item needs a
human review trail: a named author, a named verifier, a source you can open, a
sandbox image digest and pinned input-file hashes. Its tier ladder differs from
the scorer ladder above: V1 physics-verified (`oracle_compare`), V2
execution-verified (`execution_check`), V3 reference-verified
(`retrieval_metrics`, `citation_support`, `exact_match`), V4 judgment
(`rubric_judge`, voided until two humans agree). The validator is
`python -m repere_suites.rca.validate [--strict]` with rules R01 to R16.

Cost: about 100 lines of YAML per item. Fine for dozens of items, not for 700.

## 8. Known gaps (verified by reading the code, not by running it)

- `exact_match` is a `scoring.method` in the RCA harness
  (`rca/inspect_tasks.py:355`) but is not registered in any
  `make_scorer_from_spec` I found (`jev_scorers`, `sta_lta`, `lit_rag`, `dvv`,
  `synthetic_stalta`, `orchestration`, `pipeline_regression`). A BenchmarkRow that
  names it will not round-trip until it is registered.
- The RCA suite has no `export_rows`, so RCA records cannot yet become JSONL.
- `datasets/` currently holds only its README; no exported release exists in
  the tree.
- `docs/dataset_submission.md` numbers two sections 5d. Cosmetic.
- Four documents describe one process. This page does not replace them; link
  to it rather than copying from it.
