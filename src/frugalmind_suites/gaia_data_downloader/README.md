# GAIA data-downloader golden suite

This suite evaluates the [`gaia-data-downloader`](https://github.com/uw-ssec/rse-plugins/tree/main/community-plugins/gaia-data-downloader)
agent on 30 multi-domain coding tasks: write a Python script that downloads
a constrained slice of an upstream geoscience dataset under given CLI
constraints. Scoring is sandboxed-execution + structural-checksum +
trajectory-quality.

## Where things live (cross-repo)

| Repo | Role | Files |
|---|---|---|
| `uw-ssec/rse-plugins/community-plugins/gaia-data-downloader` | Agent code under test | The agent itself. Never imported by this suite. |
| `uw-ssec/gaia-agentic-ai` | Scientific home + task authoring | Design doc, GitHub issue template, scientific community. **Tasks are authored as issues here.** |
| `frugalmind` (this repo) | Eval framework + canonical truth set | `tasks.yaml`, `inspect_tasks.py`, `provenance.yaml`. |

The full design rationale (schema, scoring axes, contamination defenses,
AstaBench/Inspect AI mapping, frugalmind handoff) lives in the gaia-agentic-ai
repo at [`project-resources/handoff/golden-suite-design.md`](https://github.com/uw-ssec/gaia-agentic-ai/blob/main/project-resources/handoff/golden-suite-design.md).

## Files

| File | Authored or generated? | Purpose |
|---|---|---|
| `README.md` | authored | This file. |
| `provenance.yaml` | authored | Declares the upstream issue-tracker as source of truth. |
| `tasks.yaml` | generated | The 30-task canonical truth set. Rebuilt by `scripts/sync_gaia_tasks.py` from gaia-agentic-ai issues labelled `golden-task`. |
| `inspect_tasks.py` | authored | Inspect AI `@task` definitions (one per difficulty). |
| `scorers.py` | TODO | Execution + structural-checksum + trajectory + tool-efficiency scorers (Phase 2.1 work). |

## Re-build steps

```bash
# 1. Pull the latest issues from gaia-agentic-ai and refresh tasks.yaml:
python scripts/sync_gaia_tasks.py --release v0.1.0

# 2. Run the suite (Inspect AI):
inspect eval src/frugalmind_suites/gaia_data_downloader/inspect_tasks.py \
  --model anthropic/claude-sonnet-4-6 --max-samples 30

# 3. Refresh the leaderboard:
pixi run export-leaderboard
```

## Inventory (v0.1)

- 30 tasks total: 25 public/validation + 5 private/test
- Difficulty: 10 easy / 15 medium / 5 hard
- Domains: 7 seismic / 7 hydrology / 6 dem / 8 climate / 2 cross

## Contamination policy

Mirrors STA/LTA's split policy. Public issues describe acceptance criteria
in prose; literal expected checksums and full reference fixtures live under
`$FM_GAIA_GOLDEN_DIR` (gitignored). Tasks with `contamination_risk: high`
default to `visibility: private`.
