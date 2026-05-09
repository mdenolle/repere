# FrugalMind curated benchmark datasets

This folder is the canonical home for **frozen `(prompt, gold)` artifacts**
exported from every FrugalMind suite. Layout:

```
datasets/
└── <dataset_id>/                 # e.g. sta_lta, geobench, climbench
    └── <version>/                # e.g. v0.1
        ├── <suite_id>.jsonl      # one JSON object per line
        ├── ...
        └── manifest.json         # sha256 + row counts per file
```

## Why a separate format

`events.yaml` (and any future event/case file) is the **living** source of
truth. JSONL exports here are immutable snapshots that:

- pin a leaderboard row to a specific dataset hash,
- can be uploaded to Hugging Face without leaking private repo internals,
- give external submitters a self-contained schema.

## Row schema (`frugalmind.export.BenchmarkRow`)

```jsonc
{
  "id":           "sta_lta/intent_extraction/nisqually-2001",
  "dataset_id":   "sta_lta",
  "suite_id":     "intent_extraction",
  "version":      "v0.1",
  "task_kind":    "extraction",
  "split":        "validation",
  "visibility":   "public",
  "prompt":       "...",
  "gold":         {...},
  "scorer_spec":  {"name": "json_extraction", "config": {...}},
  "metadata":     {"event_id": "nisqually-2001", "category": "...", ...}
}
```

- `scorer_spec` is reconstructed at run time by
  `frugalmind_suites.<family>.scorers.make_scorer_from_spec`. New suites
  must register their scorers there to remain JSONL-portable.
- `visibility=public` rows may be redistributed; `private` rows should
  stay in `FM_*_GOLDEN_DIR` or a gated HF dataset.

## Exporting

```bash
# Every registered suite, default version per suite:
pixi run export-suite

# A specific suite, custom output dir, public split only:
pixi run export-suite --suite sta_lta.intent_extraction \
                      --visibility public \
                      --out datasets/

# Pin everything to a release tag:
pixi run export-suite --version v0.2-rc1 --out datasets/
```

The exporter writes one `manifest.json` per `<dataset>/<version>/` directory
with the SHA-256 hash of every JSONL file. Pin those hashes in leaderboard
rows to detect drift.

## Adding a new suite (the standard)

A suite ships in this format if and only if it implements:

1. Class attributes `dataset_id`, `suite_id`, `version`.
2. `export_rows()` yielding `BenchmarkRow` objects.
3. Scorers reconstructable from a JSON-serializable `scorer_spec` via the
   suite-family's `make_scorer_from_spec`.

`tests/test_export.py` enforces these contracts.

## Future: Hugging Face upload

Once a `<dataset>/<version>/` directory is approved, mirror it to a HF
dataset repo. The manifest already provides everything needed for a HF
`README.md` `dataset_info` block.
