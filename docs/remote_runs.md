# Running on the private GPU host, publishing to the public board

Audience: whoever operates the eval host. Companions:
[`holdout_policy.md`](holdout_policy.md) (what must never enter the repository),
[`glossary.md`](glossary.md) (what every field means).

The arrangement: evaluations run on a GPU host behind the VPN, which holds the
held-out splits and serves local models through Ollama. The board is public on
GitHub Pages. The host pushes to git directly over SSH.

## 1. Why the split is easy, and where the risk moved

Three things already fit:

- [`pages.yml`](../.github/workflows/pages.yml) deploys a committed
  `site/data/` as-is, and only generates a smoke board when none exists. CI
  never needs to reach the host.
- Held-out splits already live outside the repository, in
  `$REPERE_EVAL_DATA_DIR`. A private host is their natural home rather than an
  awkward exception.
- Scorer specs are JSON-serialisable by design, so a public reader can see
  *how* a number was scored without running anything of ours.

One file crosses the boundary: the board payload. Everything else stays.

So the risk moved. It used to be "held-out data gets committed"; it is now
"held-out data gets *published*", and an automated push has no human between
the run and the page. That is what [`repere/publish.py`](../src/repere/publish.py)
is for.

## 2. Machine independence: what is invariant, what is not

Every number on the board is one of two kinds, and conflating them is the
easiest way to publish a wrong finding.

| Kind | Fields | Rule |
|---|---|---|
| **Invariant** | `score_mean`, `score_runs`, tokens, `cost_usd`, the frontier flags, all consistency except resource | Should be identical on any machine given the same pinned inputs. If one changes when the host changes, that is a bug, not a result |
| **Host-bound** | `latency_s_mean`, `latency_s_ci95`, `consistency_resource`, energy and carbon when they land | Cannot be compared across machines at all. Carried with a `host_id`; the renderer must refuse to plot them across hosts |

`consistency_resource` is in the second group for a non-obvious reason: it
averages a coefficient of variation over cost, latency and tokens, and latency
is in there, so the whole metric inherits the binding even though two of its
three inputs do not. The authoritative list is
`repere.provenance.HOST_BOUND_FIELDS`.

A 7B model is not "slower than" a cloud model because one ran on four GPUs and
the other over an API. That comparison is a property of the hosts.

### The pin that makes invariance real

**A tag is not a pin.** `qwen2.5:7b` is a moving pointer: Ollama can serve a
different quantization on two machines under the same name, and the board would
render that difference as a model difference.

`repere_suites.rca.cost` already flags API models whose id is not pinned, but
[exempts local providers](../src/repere_suites/rca/cost.py) from the check —
precisely the case a private GPU host makes dangerous.
`repere.provenance.capture_ollama_models` closes it by recording the digest,
quantization level and parameter size Ollama reports for every model served. A
local model with no digest is `pinned = False`, and the publish step warns.

Pin the digest in your run notes, not just the tag. When you pull a new
`qwen2.5:7b`, the old rows are not comparable to the new ones.

## 3. Installing on the eval host

A one-time runbook. Everything after this is `pixi run`.

### 3.1 Prerequisites

```bash
# pixi manages the whole Python side from pixi.lock; nothing else is needed.
curl -fsSL https://pixi.sh/install.sh | bash
exec "$SHELL" -l                       # put ~/.pixi/bin on PATH

# Docker, only if you will run the sandboxed code-execution suites.
docker --version && nvidia-smi
```

### 3.2 The repository

```bash
git clone git@github.com:mdenolle/repere.git
cd repere
pixi install                           # resolves from pixi.lock, no network drift
pixi run -e default pytest             # all pass, same suite as CI; no failures allowed
```

If that test run is not green, stop here. It is the same suite CI runs, and a
failure on the host before any eval has happened is an environment problem, not
a result.

### 3.3 Ollama and the local models

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama

# Four GPUs: let Ollama use all of them, and keep models resident between
# samples so a 5-epoch sweep is not five cold starts.
sudo systemctl edit ollama    # add, then restart:
#   [Service]
#   Environment="CUDA_VISIBLE_DEVICES=0,1,2,3"
#   Environment="OLLAMA_KEEP_ALIVE=30m"
#   Environment="OLLAMA_MAX_LOADED_MODELS=2"

ollama pull qwen2.5:7b && ollama pull llama3.1:8b
ollama pull deepseek-r1:7b && ollama pull olmo2:7b

# The size ladder (registered in config/models.yaml). Every one fits on a
# single A100 80GB at the default ~4-bit tag; the largest, qwen2.5:72b, is
# 47.4 GB. Same quantization at every size, so a family's curve is a size
# effect. qwen2.5:72b ships under the Qwen Research License.
for m in qwen2.5:14b qwen2.5:32b qwen2.5:72b \
         deepseek-r1:14b deepseek-r1:32b deepseek-r1:70b \
         olmo2:13b llama3.3:70b; do ollama pull "$m"; done
ollama list                            # record the digests; see 3.6
```

`OLLAMA_MAX_LOADED_MODELS=2` is deliberate on a 4-GPU box: loading more models
than that concurrently trades throughput for eviction churn, and a sweep runs
one model at a time anyway.

### 3.4 Secrets and the held-out data

```bash
export REPERE_EVAL_DATA_DIR=/srv/repere/private     # gitignored, never in the tree
mkdir -p "$REPERE_EVAL_DATA_DIR"
pixi run -e full python scripts/pull_eval_data.py   # needs gated HF access

cp .env.example .env 2>/dev/null || touch .env      # ANTHROPIC_API_KEY for the
                                                    # cloud reference row only
chmod 600 .env
export REPERE_HOST_LABEL="ess-gpu-01"               # appears in provenance
```

Put the two exports in the service environment or the operator's profile, not
in the repository.

### 3.5 Git push from the host

The SSH credentials are already in place, so nothing to configure beyond an
identity on the commits:

```bash
git config user.name  "Repère eval host"
git config user.email "repere-host@uw.edu"
git remote -v                          # must be the SSH remote, not HTTPS
ssh -T git@github.com                  # expect the "successfully authenticated" line
```

### 3.6 Verify before the first real sweep

Three checks, in order. Each one has caught a real problem.

```bash
# 1. What does the host actually see, and are the weights pinned?
pixi run -e default python -c "
from repere.provenance import capture_run_provenance
p = capture_run_provenance()
print(p.host.gpu_summary, '| ollama', p.host.ollama_version)
for m in p.models: print(m.model_id, m.digest, m.quantization, 'pinned' if m.pinned else 'UNPINNED')
for w in p.warnings(): print('warning:', w)
"

# 2. The fresh-clone view. This host is the one machine where forgetting the
#    held-out policy is invisible, because it always has the private data.
mkdir -p /tmp/no-private
REPERE_EVAL_DATA_DIR=/tmp/no-private pixi run -e default pytest

# 3. A dry publish: builds the board, runs the outbound guard, writes nothing
#    anywhere public.
pixi run -e default python scripts/publish_board.py \
    --results-dir results --output /tmp/board-dry.json
```

Record the digests from check 1 in the run notes. When you later `ollama pull`
a new `qwen2.5:7b`, the old rows are not comparable to the new ones, and the
digest is the only thing that will tell you.

### 3.7 Running a sweep

```bash
# The deterministic suites, five epochs, every item (never --limit on a run
# meant for the board: a capped run replaces the full one). Temperature 0.7,
# not 0: repeats at T=0 return near-identical text and give error bars that
# measure nothing.
pixi run -e full python scripts/demo_dashboard.py --live --repeats 5 --temperature 0.7

# The size ladder in the same run, so every row shares one protocol and host.
pixi run -e full python scripts/demo_dashboard.py --live --repeats 5 --temperature 0.7 \
    --models qwen2.5:7b qwen2.5:14b qwen2.5:32b qwen2.5:72b \
             deepseek-r1:7b deepseek-r1:14b deepseek-r1:32b deepseek-r1:70b \
             olmo2:7b olmo2:13b llama3.1:8b llama3.3:70b \
             claude-haiku-4-5-20251001

# The RCA harness, which already understands epochs.
pixi run -e full python -m repere_suites.rca.run \
    --family coding --epochs 5 --seed 0 --sandbox docker
```

Budget note: on 7-8B local models a single full sweep is hours, and the three
robustness phases multiply that. Start with the baseline phase on every arm and
add robustness on a subset.

## 4. Publishing

```bash
pixi run -e default python scripts/publish_board.py \
    --results-dir results --host-label "$REPERE_HOST_LABEL" \
    --epochs 5 --seed 0 --temperature 0.7
```

It builds v0.2 rows, attaches provenance, stamps `host_id` on every row, runs
the guard, and writes only if the guard passes. Add `--commit --push` once you
have watched it pass a few times; it refuses to commit while warnings stand
unless you also pass `--allow-warnings`.

### What the guard enforces

1. **An allowlist of row fields.** Not a denylist — that fails open the moment
   someone adds a field. A new board field must be added to
   `PUBLISHABLE_ROW_FIELDS` on purpose, in the same commit.
2. **No free text.** Every published value is a number, a boolean, a null, or a
   string from a closed vocabulary. Scorer explanations, prompts, completions,
   Jev claim text and source passages are all unrepresentable in a row, and
   those are where the answers live.
3. **No held-out vocabulary anywhere** in the payload: `expected_detection`,
   `stalta_params`, `expected_tools`, `SECRET_SEED` and friends.

It raises rather than filtering. Silently dropping a field would let you believe
you published something you did not.

### What must never cross, with or without the guard

| Artefact | Why |
|---|---|
| `$REPERE_EVAL_DATA_DIR/**` | it is the gold |
| `results/rca/*/samples.jsonl` | the per-sample `explanation` can state the oracle's reference value |
| telemetry JSONL | carries prompts and completions verbatim |
| Jev detail records | carry the claim text and the source passage |
| per-item scores on the **test** split | see below |

That last one is the subtle one. Publishing per-item scores on the hidden split,
run after run, turns the board into an oracle in slow motion: enough published
rows and a reader reconstructs which held-out items each model passes. Publish
suite-level aggregates for the test split; per-item detail only for validation.

## 5. What the public gets instead of reproducibility

Nobody outside the VPN can rerun these numbers, so the board has to carry enough
to attribute them. The provenance block holds:

| Field | Why a reader needs it |
|---|---|
| `harness_commit`, `harness_dirty` | which code produced the number; a dirty tree means the commit does not describe the run |
| `models[].digest`, `quantization` | which weights, not which tag |
| `host.host_id`, `gpu_models`, `ollama_version` | which machine, for the host-bound fields |
| `sandbox_image` | the execution environment for code-running suites |
| `price_map_version` | what the dollar figures were computed against |
| `dataset_sha256` | the frozen inputs, checkable against `datasets/*/manifest.json` |
| `seed`, `temperature`, `n_epochs` | the run protocol |

The site should say plainly: these numbers were produced on a private host; what
you can verify independently is the dataset hashes, the scorer specifications
and the harness commit; what you cannot verify is the runs themselves. That is a
weaker claim than a fully public benchmark makes, and stating it is better than
implying otherwise.

## 6. One upside of a fixed machine

Energy and carbon per run (issue #39) become measurable in a way a laptop never
allowed: a known GPU inventory, a stable power draw, one grid region. It is the
axis most likely to complicate the frugality story, which is exactly why it is
worth having, and the private host is what makes it collectable.
