# Submitting a dataset to Repère

This is the contributor guide for adding an evaluation dataset. It covers the
**strict row schema**, the **public/hidden split policy** that keeps scores
honest, the **Hugging Face hosting design** (proposed), and the concrete
**PR checklist**.

The governing principle: **a benchmark is only worth its leakage discipline.**
If gold answers leak into training data, the score measures memorization, not
capability. Everything below is in service of that.

---

## 1. The two-split model

Every item declares a `split` and a `visibility`:

| split | visibility | Lives where | Purpose |
|-------|-----------|-------------|---------|
| `validation` | `public` | committed to the repo / public HF dataset | develop against, iterate scorers, reproduce the demo leaderboard |
| `test` | `private` | gated store, **gold never distributed** | the number that goes on the ranked leaderboard |

You develop and debug on `validation`. You are scored on `test`, whose gold you
never see. This mirrors held-out ML practice and is the single most important
thing that separates an evidence benchmark from a leaderboard people overfit to.

`cutoff_date` is the third guard: it bars a retrieval-augmented agent from using
information it could not have had at the time (a catalog entry published after
the event, a paper that post-dates the question). A correct answer obtained with
future knowledge is cheating even when it is correct.

---

## 2. The strict row schema

Datasets serialise to one JSON object per line (JSONL), one object per
`(prompt, gold)` pair. The schema is [`repere.export.BenchmarkRow`](../src/repere/export.py)
— treat it as the contract:

```json
{
  "id":           "pipeline_regression/pipeline_regression/phasenet-p-picks-nc",
  "dataset_id":   "pipeline_regression",
  "suite_id":     "pipeline_regression",
  "version":      "v0.1",
  "task_kind":    "numerical_regression",
  "split":        "validation",
  "visibility":   "public",
  "prompt":       "…",
  "gold":         [12.34, 41.87],
  "scorer_spec":  {"name": "numerical_regression",
                   "config": {"artifact_key": "p_picks", "metric": "pick_f1",
                              "tolerance": 0.5}},
  "metadata":     {"pipeline_id": "…", "tool": "seisbench"}
}
```

Rules that make a row **valid** (enforced by tests + the exporter):

1. **`id` is globally unique** and of the form `dataset_id/suite_id/item_id`.
2. **`task_kind`** is one of the [`TaskKind`](../src/repere/__init__.py) enum
   values (`extraction`, `code_generation`, `plotting`, `report_drafting`,
   `numerical_regression`, `retrieval`, `translation`, `grounded_qa`,
   `orchestration`). Add a member if you truly need a new one.
3. **`scorer_spec` is self-contained and serialisable** — `{"name", "config"}`,
   where `name` resolves in your suite's `make_scorer_from_spec`. This is what
   lets the row be scored by anyone, anywhere, without your Python.
4. **`split` ∈ {validation, test}`, `visibility` ∈ {public, private}`.**
5. **`gold` is JSON-serialisable** and matches what the scorer expects (a dict
   for `json_extraction`, a numeric array for `numerical_regression`, a relevant
   -id list for `retrieval_metrics`, …).
6. **`version`** bumps whenever prompts or golds change; the exporter records a
   sha256 of every JSONL file in a sidecar `manifest.json` so a leaderboard row
   pins to an exact dataset version.

### Why the spec-travels-in-the-row design

Repère never ships a scorer as an opaque callable in the dataset. It ships a
**declarative spec** and reconstructs the callable at score time. That is what
makes a row portable to Hugging Face, to `inspect_evals`, and to a server-side
scorer — and what makes the hidden-split design below possible.

---

## 3. How to author a suite (mechanics)

The clean insertion pattern (all four families follow it):

1. **Truth set** — a YAML file (`events.yaml` / `pipelines.yaml` / `tasks.yaml`)
   holding your items, each with `split`, `visibility`, and the fields your
   prompt/gold need. Keep it parametric where possible so N items derive from
   one source of truth.
2. **Scorer** — a factory in your suite's `scorers.py`, registered in
   `make_scorer_from_spec`. Push it as far up the
   [scorability spectrum](#4-grading-easy--hard) as the task allows; reuse an
   existing scorer if one fits (`numerical_regression`, `retrieval_metrics`, …).
3. **Suite** — a `DenolleGroupSuite` subclass with `_compose(item) -> (prompt,
   gold, scorer_spec, meta)` feeding **both** `items()` (runtime) and
   `export_rows()` (curation). One `_compose`, zero drift.
4. **Inspect tasks** — thin `@task` wrappers in `inspect_tasks.py` reusing
   `_compose`, plus a generic `@scorer` that dispatches on
   `sample.metadata['scorer_spec']`.
5. **Tests** — unit-test the scorer math and round-trip the suite
   (`export_rows` / `items`). See `tests/test_numerical_regression_scorer.py`
   for the template.

The `gaia_data_downloader` stub is the ready-made template for a sandbox-scored
coding task; `lit_rag` and `pipeline_regression` are templates for
deterministic scorers.

---

## 4. Grading easy → hard

Every scorer sits on a **scorability spectrum**; contribute at the highest tier
your task supports.

| Tier | Gold | Scorer examples | Judge noise |
|------|------|-----------------|-------------|
| T0 deterministic | exact/structured value | `json_extraction`, `term_preservation`, `citation_support`, `retrieval_metrics` | none |
| T1 numerical | reference array/scalar | `numerical_regression` | none |
| T2 perceptual | reference artifact | `plot_ssim` | low |
| T3 trajectory | reference process/DAG | `trajectory_dag` | low–med |
| T4 rubric | criteria, no single gold | LLM-judge (fallback only) | high |

**Difficulty** is also a property of the *data*, not just the scorer: harder
stations, ambiguous windows, negative cases (a window that should yield *no*
detection — the regression analogue of `expected_detection: false`), and
tighter tolerances. Label difficulty in `metadata` (`easy`/`medium`/`hard`) so
the leaderboard can slice by it.

---

## 5. Hugging Face hosting (proposed design)

> Status: design. Roadmap items **P2.3** (move large goldens to DVC/HF) and
> **P3.3** (hidden test split via gated HF with server-side scoring) track the
> implementation.

We want three things at once: (a) easy `pull` of public data for development,
(b) large golden artifacts out of git, and (c) hidden test gold that is *never
distributed*. A two-repo layout on Hugging Face does all three.

### 5a. Public dataset repo — `repere/<dataset>` (open)

- Contains **only** `validation` / `public` rows and any large public artifacts
  (plot goldens, corpora) that are painful in git.
- Pulled with `datasets.load_dataset("repere/<dataset>", split="validation")`
  or a `pixi run pull-dataset <name>` helper backed by the HF CLI / DVC remote.
- Carries the `manifest.json` sha256 set so a pulled copy is verifiably the
  version a leaderboard row was scored against.
- **No `gold` for any `test` row appears here.** Public rows may ship a
  redacted twin (prompt only) so tooling can *see* a hidden item exists without
  its answer.

### 5b. Hidden test repo — `repere/<dataset>-test` (gated)

- **Gated** (HF access request / org membership). Access is granted to the
  scoring service, not to model developers.
- Scoring is **server-side**: a submission sends model *outputs* for the hidden
  prompts; the service runs `make_scorer_from_spec` against the gold it holds and
  returns only the aggregate score. Gold never leaves the server.
- Because `scorer_spec` is declarative and self-contained, the server needs no
  submitter code to score — it reconstructs the scorer from the spec.

### 5c. The `pull` for benchmarking vs developing

Two commands, two trust levels:

```bash
# Develop: the PUBLIC validation split ships in-repo. Nothing to pull.
#          Reproduce the demo board on a laptop with no credentials.

# Benchmark: pull the HIDDEN test split (gated dataset, requires access).
huggingface-cli login          # or export HF_TOKEN=hf_...
pixi run -e full python scripts/pull_eval_data.py
#   -> data/private/  (gitignored; suites pick it up automatically)
```

### 5d. Implemented: how the hidden split actually works

This is live for `synthetic_stalta` and is the pattern to copy.

- **Public validation split** (`src/repere_suites/synthetic_stalta/cases.yaml`)
  is committed on purpose: it is the development set, and it keeps the demo board
  reproducible by anyone.
- **Hidden test split** is *not* in git. Crucially, it is also **not
  regenerable from the repo**: every transform in it (event delay, amplitude,
  noise level, second-event gap) is drawn from a **secret master seed** supplied
  at build time and stored with the gated dataset, never committed.

  ```bash
  # Maintainers only. Never commit the seed.
  python scripts/build_synthetic_stalta.py --split test --secret-seed <SECRET>
  #   -> data/private/synthetic_stalta_test.yaml   (gitignored)
  #   then upload that file to the gated HF dataset
  ```

  Without the seed you cannot reconstruct the answers even though you have the
  generator and the public waveform. Publishing the generator is therefore safe.

- **The loader merges** the hidden split when present and degrades gracefully
  when it is not: `split="validation"` always works (CI, a fresh clone), while
  `split="test"` raises a clear error telling you to pull, rather than silently
  scoring on the public split.

- **Two tests enforce the contract**: the committed `cases.yaml` must contain
  *only* `validation`/`public` rows, and requesting the test split without the
  data must fail loudly.

> **A gitignore alone is not protection.** If the generator and its seed are both
> public, the "hidden" answers can be reproduced exactly. Hiding the *seed* — not
> just the file — is what makes the split real.

### 5d. Anti-leakage measures (do all of these)

- **Never commit or upload `test` gold** to any public location. The
  public/private split in the row schema is the mechanical guard; CI should fail
  a PR that puts a `test` row's `gold` in a public file.
- **Canary string.** Embed a unique, searchable canary GUID in the hidden set's
  documentation so you can later detect if it was scraped into a training
  corpus.
- **`cutoff_date` on every item** so retrieval agents cannot time-travel.
- **Version + hash pinning.** A score is meaningless without the dataset version
  it was computed on; `manifest.json` sha256 makes drift detectable.
- **Rotate the hidden set.** Periodically retire and replace hidden items;
  a static hidden set slowly leaks through submissions and public discussion.
- **Decontamination note.** Ask model submitters to attest their training data
  excludes the canary / public prompts, and document the attestation next to the
  leaderboard row.
- **Human-review promotion.** A `validation` item is promoted to a citable
  public golden only after a human verifies the catalog match / source (existing
  policy; see [README §Golden datasets](../README.md#golden-datasets)).

---

## 6. PR checklist

- [ ] Truth-set YAML with `split` + `visibility` on every item; `cutoff_date`
      where retrieval is possible.
- [ ] Scorer factory registered in `make_scorer_from_spec`; at the highest
      scorability tier the task allows; reuses an existing scorer if one fits.
- [ ] Suite subclass with a single `_compose` feeding `items()` +
      `export_rows()`.
- [ ] `@task` wrappers + generic spec-dispatching `@scorer`.
- [ ] Tests: scorer math + suite round-trip; `ruff check` clean.
- [ ] **No `test`/`private` gold in any public file.**
- [ ] `version` set; run the exporter and commit the `manifest.json` diff.
- [ ] A short design doc under `docs/` if you introduced a new scorer or
      `TaskKind` (see `docs/numerical_regression_scorer.md` for the shape).

See also: [`docs/lit_rag_scorers.md`](lit_rag_scorers.md),
[`docs/numerical_regression_scorer.md`](numerical_regression_scorer.md),
[`docs/orchestration_scorer.md`](orchestration_scorer.md),
[`docs/leaderboard_conditions.md`](leaderboard_conditions.md),
[`ROADMAP.md`](../ROADMAP.md).
