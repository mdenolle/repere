# Held-out data policy: how a new golden set stays hidden

Audience: anyone adding a suite or a golden set to Repère, including future
Marine. Companion to [`golden_data_provisioning.md`](golden_data_provisioning.md),
which decides *how* hidden gold is held (derived from a secret, or hosted
gated). This document is narrower: it is the procedure that keeps a new golden
set out of the repository and out of the published package, and the enforcement
that makes the procedure hard to skip.

## What went wrong, once, so it is not repeated

Nine rows marked `split: test, visibility: private` were committed inside
`src/repere_suites/` — four `sta_lta` events and five `gaia_data_downloader`
tasks — and were published in the `repere` 0.5.1 wheel on PyPI.

Three things had to line up:

1. **The rows were the gold, not pointers to it.** An `sta_lta` test row states
   `expected_detection`, the reference `stalta_params` and the station picks. A
   GAIA test row states `expected_tools`, `required_cli_args` and the
   `expected_files` globs. Marking a row `visibility: private` documented an
   intention; it did not move the answers anywhere.
2. **`.gitignore` could not help.** It guards `data/` and `data/golden_private/`.
   Truth sets live inside the package, under `src/repere_suites/`, which is
   version-controlled by design because the public validation split belongs
   there.
3. **`package-data` publishes by definition.** Once
   `[tool.setuptools.package-data]` matched `*.yaml` under a suite, every row in
   those files went into the wheel. Nothing warned, because shipping suite data
   is the correct behaviour — the contents were wrong, not the mechanism.

Four exported fixtures under `tests/fixtures/sta_lta.*.test.json` carried the
same gold independently, with the reference `stalta_params` written out in the
prompt text.

**The lesson in one line: "held out" has to mean held out of the repository
*and* out of the distribution, and it has to be checked by something other than
the author's intention.**

## The rule

> A row that a ranked score is computed from never exists inside `src/`, at any
> commit, in any branch.

"At any commit" matters. Git history is permanent, and a public repository
publishes its history. A held-out row that is committed and then removed is
still compromised — recoverable with one `git log -S`. Moving it later limits
future damage; it does not undo the disclosure.

## Where held-out data lives

One canonical home, the same one the synthetic split already used:

```
$REPERE_EVAL_DATA_DIR                     # default: <repo>/data/private/ (gitignored)
├── sta_lta_test.yaml                     # held-out event rows
├── gaia_data_downloader_test.yaml        # held-out task rows
├── synthetic_stalta_test.yaml            # gold onsets for the generated split
├── SECRET_SEED                           # the generator seed (Mode A suites)
└── fixtures/
    └── sta_lta.<suite>.test.json         # exported held-out prompts + gold
```

Naming: `<suite_package>_test.yaml`, with **the same top-level shape as the
public file** (`events:` / `tasks:` / `cases:`), so a loader can merge it
verbatim with no translation layer.

Distribution: the gated Hugging Face dataset, pulled by
`scripts/pull_eval_data.py` into `$REPERE_EVAL_DATA_DIR`. See
[`golden_data_provisioning.md`](golden_data_provisioning.md) for the gating and
the derive-vs-host decision.

## Authoring a new golden set

The order of these steps is the whole point. Author held-out rows **into the
private directory directly** — never in the repo tree "temporarily", never in a
branch you plan to clean up later.

1. **Decide the split before you write a row.** Validation rows are public and
   go in the package. Test rows are held out. A row does not change category
   later; if you need more public rows, write new ones.
2. **Write the public validation rows** into
   `src/repere_suites/<suite>/<truthset>.yaml`. These are the development
   surface: contributors reproduce the demo board with them, reviewers read
   them in a PR.
3. **Write the test rows straight into `$REPERE_EVAL_DATA_DIR/<suite>_test.yaml`.**
   Same shape. They never touch the working tree of the repository.
4. **Record provenance without the answers.** The suite's `provenance.yaml`
   says where the held-out partition lives, how it is distributed, and what the
   contamination risk is. It does not restate any expected value.
5. **Upload to the gated dataset** so the partition is not only on your laptop.
6. **Run `pytest`.** The guards below either pass or tell you what leaked.

## The loader contract a new suite must implement

Copy `sta_lta/items.py` or `gaia_data_downloader/inspect_tasks.py`. Five
properties, each of which exists because its absence caused a real bug:

| Property | Why |
|---|---|
| `HIDDEN_PATH = PRIVATE_DIR / "<suite>_test.yaml"`, and `PRIVATE_DIR` honours `REPERE_EVAL_DATA_DIR` | one home, one env var, so pulling the gated dataset is enough to configure every suite |
| Merge the partition **only when reading the packaged file** | a caller that passes an explicit path (the validation unit tests) must see exactly that file |
| Both partitions go through **one shared validator** | a malformed held-out row must fail at load, not on the run that decides a ranked score |
| An id present in both partitions is an **error**, not an override | silent precedence hides an authoring mistake |
| `split="test"` with no test rows raises `FileNotFoundError` **naming the expected path** | returning zero rows silently is how a hidden split becomes an invisible one — the same failure mode as the `package-data` bug, where a wheel imported cleanly and enumerated nothing |

## Enforcement

Four layers. The first two are new in v0.5.2 and each has a negative-control
test, because a guard nobody has seen fail is a guess.

1. **`tests/test_no_holdout_in_repo.py`** — no committed truth set may contain a
   `split: test` or `visibility: private` row, and no file matching a held-out
   naming convention may sit inside the package. Verified by reintroducing a
   canary row and watching both assertions fire.
2. **`.github/workflows/tests.yml`** — the full suite on every pull request and
   every push to `main`, with no paths filter. Without this the guard above only
   ran on a contributor's laptop, which is exactly how the leak shipped.
3. **`tests/test_suite_fixtures.py::test_no_holdout_fixture_is_committed`** —
   no `*.test.json` under `tests/fixtures/`. `build_suite_fixtures.py` defaults
   to the validation split and routes `--splits test` into
   `$REPERE_EVAL_DATA_DIR/fixtures/`.
4. **`.github/workflows/publish.yml`** — before uploading to PyPI, the built
   wheel is installed into a throwaway venv and every suite is loaded with cwd
   `/`. That catches both directions: data that should ship and is missing, and
   data that ships and should not.

### Reproducing the fresh-clone view locally

Your machine has the held-out partition; CI, contributors and anyone who runs
`pip install repere` do not. Point the env var at an empty directory to see what
they see, before you open the PR:

```bash
mkdir -p /tmp/no-private
REPERE_EVAL_DATA_DIR=/tmp/no-private pytest
```

This is not hypothetical. `tests/test_sta_lta_suite.py` asserted
`len(_load_events()) >= 6` and required all four event categories; it passed on
the authoring machine and failed on the first CI run after the split, because
two of the four categories -- `noise_day` and `quarry_blast` -- are held-out
rows. Any test that asserts a count or a category set over the *merged* truth
set has to skip when the partition is absent.

### A consequence worth fixing: the public split is all-positive

`noise_day` and `quarry_blast` are both held out, so the public validation split
contains two positive cases and no negative one. The suite's design says the
opposite -- "a model that scores 1.0 on Nisqually but hallucinates an earthquake
on a noise day is a worse model" -- and a contributor developing against the
public split never meets a case whose right answer is "no event".

The cheap repair: the two burned rows that carry those categories
(`pnsn-quiet-day-VERIFY`, `cascade-quarry-blast-VERIFY`) are already public via
the 0.5.1 wheel and are both flagged `NEEDS VERIFICATION`, so demoting them to
public validation rows costs nothing that has not already been spent, and
restores negative-case coverage where contributors can see it. Re-cut the
held-out negative cases from events that have never been published.

Still worth adding, in rough priority order:

- **Secret scanning and push protection.** Free on a public repository and now
  applicable, since `mdenolle/repere` is public. One API call or one settings
  toggle; it blocks credential pushes rather than reporting them afterwards.
- **A guard on the sdist as well as the wheel.** The publish workflow inspects
  the wheel; an sdist built from a dirty tree could differ.
- **Gate `ruff`.** Not yet: 82 pre-existing findings mean a gate fails on
  arrival. Clear them, then add `pixi run lint` to `tests.yml`.

## Re-cutting a compromised split

The nine rows published in 0.5.1 are compromised and cannot be repaired by
moving them. Any model trained or evaluated after September 2026 may have seen
them, and 0.5.1 remains installable by exact pin even after being yanked.

To re-cut:

1. Choose events or tasks that have **not** appeared in this repository, its
   history, any published wheel, or any issue tracker. For `sta_lta` that means
   new catalog events, not a re-labelling of the existing four.
2. Write them straight into `$REPERE_EVAL_DATA_DIR` per the procedure above.
3. Leave the burned rows out entirely, or demote them to public validation rows
   where their disclosure costs nothing. Do not keep them as a test split.
4. Note the re-cut in `CHANGELOG.md` with the date the old split was retired, so
   a published number can be attributed to one split or the other.
5. Resolve the `VERIFY` markers before any of it becomes a ranked benchmark. Two
   of the four burned `sta_lta` rows still carry
   `DATE/CATALOG_ID NEEDS VERIFICATION`.

## Checklist for a pull request that touches golden data

- [ ] No new row in `src/` has `split: test` or `visibility: private`.
- [ ] Held-out rows were authored in `$REPERE_EVAL_DATA_DIR`, never committed
      and removed.
- [ ] The loader implements all five properties of the contract above.
- [ ] `provenance.yaml` describes the partition without restating an answer.
- [ ] `pytest` passes locally, including `tests/test_no_holdout_in_repo.py`.
- [ ] `REPERE_EVAL_DATA_DIR=/tmp/no-private pytest` also passes: no test may
      depend on the held-out partition without skipping when it is absent.
- [ ] The held-out partition is in the gated dataset, not only on one laptop.
- [ ] If `package-data` gained a pattern, a wheel was built and inspected.
