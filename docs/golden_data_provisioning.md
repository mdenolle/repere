# Golden data provisioning: derive it, or host it?

`dataset_submission.md` §1 sets the rule that matters: the `test` split's gold is
**never distributed**. This document is about the mechanics of honouring that,
because there are two very different ways to hold hidden gold, and suites in this
repo need both.

| Mode | Hidden gold is... | Credential | Example |
| --- | --- | --- | --- |
| **A. Derived** | *regenerated on demand* from a secret | one secret | `codameter` (synthetic dv/v) |
| **B. Hosted** | *stored* in a gated repo (§5b) | a scoped read token | `sta_lta` (real waveforms, golden plots), lit/RAG corpora |

Pick the mode from the data, not from habit. Getting this wrong is how benchmarks
quietly leak.

---

## The decision rule

Use **Mode A (derive)** if and only if both hold:

1. The gold is a **pure function of code + a secret** — no field data, no human
   labels, no third-party corpus.
2. Regenerating it is **cheap enough to do per eval run** (minutes, not hours).

Otherwise use **Mode B (host)**. Concretely:

| The gold is... | Mode | Why |
| --- | --- | --- |
| synthetic, seeded, cheap | **A** | nothing to store; see below |
| synthetic but **expensive** (long simulations, huge corpora) | **B** | regenerating per run is wasteful or infeasible |
| **real** (recordings, catalogs, human labels) | **B** | it is not a function of any seed; it *must* be stored |
| a **third-party** corpus | **B** | you do not control its generation |
| scored for **external submitters** | **B** | someone has to hold it server-side (§5b) |

`sta_lta` is the clean counter-example to `codameter`: its events are real
waveforms and its plot goldens are real PNGs. No secret regenerates those. It is
Mode B by nature.

---

## Mode A — derive from a secret (`codameter`)

The `codameter` dv/v suite generates its cases from recipes; a case's ground
truth is a pure function of its truth parameters. So the hidden corpus is
**stored nowhere**. The scoring job holds one secret and regenerates it:

```yaml
on:
  workflow_dispatch:                 # NOT `pull_request` from forks:
  schedule: [{cron: "0 6 * * 1"}]    # secrets are withheld there, and rightly so
  push: {branches: [main]}

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e ".[test,dvv]"

      - name: Materialize the hidden golden set
        env:
          CODAMETER_GOLDEN_SECRET: ${{ secrets.CODAMETER_GOLDEN_SECRET }}
        run: |
          python -m codameter.private_golden \
              --secret "$CODAMETER_GOLDEN_SECRET" \
              --out "$RUNNER_TEMP/hidden-golden"
          echo "CODAMETER_GOLDEN_DIR=$RUNNER_TEMP/hidden-golden" >> "$GITHUB_ENV"

      - name: Run the eval
        run: ...        # the scorer reads CODAMETER_GOLDEN_DIR
```

One repository secret. No dataset repo, no token, no bucket.

### Why derived gold is *reproducible*

`corpus = f(secret, package_version)` — deterministic, offline, no mutable state.

- **Byte-identical, forever.** The same secret and the same package version
  regenerate the same cases and the same expected metrics on any machine. Scores
  are comparable across runs because the corpus cannot drift.
- **Publishable as a commitment.** You can publish the SHA-256 of the generated
  `cases.json` *without publishing its contents*. That pins the benchmark
  cryptographically: anyone holding the secret can verify you did not quietly
  change the corpus after seeing a model's results. A hosted file gives you no
  such proof unless you separately pin its revision — which people forget to do.
- **Version-coupled by construction.** If the generator changes, the expected
  metrics are recomputed in the same job, so the oracle can never go stale
  against the code. A hosted `manifest.json` silently can.

### Why derived gold is *safe*

- **Nothing at rest.** The corpus lives only in the runner's temp dir for the life
  of the job. No bucket to misconfigure, no repo to accidentally flip public, no
  `--local-dir` copy left on a laptop.
- **One credential, not two artifacts.** The attack surface is a single secret,
  versus (a long-lived read token) x (a stored artifact) x (its ACL).
- **Rotation is free.** Change the secret and the corpus is new. Hosting means
  regenerate *and* re-upload *and* invalidate the old copy and its token.

Cost: regenerating the hidden manifest runs the full pipeline (**~2-3 min** for
codameter). That is the whole price of hosting nothing, and it is noise next to
an eval's model-call spend.

---

## Mode B — host it, gated (`sta_lta`, real-data and RAG suites)

Follow `dataset_submission.md` §5: a public repo for `validation`/`public` rows
and artifacts, a **gated** repo for the hidden `test` gold, with scoring
server-side so gold never leaves. Three requirements beyond "make it private":

**1. Pin the revision.** A gated repo is still mutable. If you pull `main`, your
benchmark can move under you and last month's scores stop meaning anything.

```bash
huggingface-cli download frugalmind/<dataset>-test \
    --repo-type dataset --revision <commit-sha> --local-dir "$RUNNER_TEMP/gold"
```

Record that revision SHA in the leaderboard row, next to the `manifest.json`
sha256 (§5a). "Which gold was this scored against" must be answerable later.

**2. Scope the token to one repo, read-only.** Use a **fine-grained** token
(HF's `read`/`write` role tokens grant everything you can see):

- select **only** `frugalmind/<dataset>-test`
- grant **read access to contents** of that repo — nothing else: no other repos,
  no org-wide read, no inference.

Better, if the eval runs in GitHub Actions: use HF
[Trusted Publishers](https://huggingface.co/docs/hub/trusted-publishers) and skip
the stored token entirely — the workflow's OIDC identity is exchanged for a
short-lived Hub token per run.

**3. Verify what you pulled.** Check the downloaded files against the
`manifest.json` sha256 set before scoring. A silent mismatch means you are not
scoring the benchmark you think you are.

---

## Invariants that hold in *both* modes

These are the ones that actually get violated in practice.

1. **The model never sees the gold.** Hand the agent an observables-only view.
   codameter enforces this with `golden.observed()`, which strips the truth keys;
   its `generate()` returns the truth *and is for the scorer only*. A suite whose
   prompt points a sandboxed agent at a loader that returns the answer is not a
   benchmark — the agent can just return it.
2. **The credential never enters the agent sandbox.** This is the real leak
   vector, and it is mode-independent. A model that can read
   `CODAMETER_GOLDEN_SECRET` can *regenerate* the hidden corpus; a model that can
   read `HF_TOKEN` can *download* it. Credentials belong to the
   scorer/orchestrator process. The sandbox gets data, never keys.
3. **The corpus is pinned.** Mode A: `(secret, package version)`. Mode B: the
   repo revision SHA. Record it on the leaderboard row either way.
4. **Nothing secret-derived goes in a shared cache.** Actions caches are reachable
   across branches (and from fork-PR workflows in some configurations). Never
   cache a generated hidden corpus or a downloaded gold directory. Regenerate or
   re-fetch each run.

## Per-suite status

| Suite | Mode | Hidden gold held as |
| --- | --- | --- |
| `codameter` (dv/v) | **A** derived | `CODAMETER_GOLDEN_SECRET` (a repo secret) |
| `sta_lta` | **B** hosted | gated HF repo (real waveforms + golden plots) |
| lit/RAG, real-data suites | **B** hosted | gated HF repo, pinned revision |

New suite? Run the decision rule above. If your gold is synthetic and cheap,
derive it — it is strictly less to secure.
