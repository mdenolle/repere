"""Dump {prompt, gold} pairs for the four parametric STA/LTA suites,
one JSON per (suite, split) pair.

The plot suite is excluded — its gold is a PNG file, handled by
scripts/build_plot_goldens.py. The other four suites are parametric over
events.yaml. Dumping their (prompt, gold) pairs lets reviewers see what
the benchmark actually asks for without running Python, and lets a drift
test catch unintended changes to either the prompt template or the gold
construction.

Outputs (default): one JSON per validation suite under tests/fixtures/, e.g.
    tests/fixtures/sta_lta.intent_extraction.validation.json
    tests/fixtures/sta_lta.fetch_code.validation.json
    ...

Each fixture lists only events from that split, so reviewers and drift
tests see exactly what `STALTAIntentExtractionSuite(split=...)` would emit.

Only the validation split is written under tests/fixtures/. A test-split
fixture contains the held-out prompts and their gold -- the reference
stalta_params appear in the prompt text -- so `--splits test` writes into
REPERE_EVAL_DATA_DIR instead, next to the held-out events themselves. Ask for
it explicitly; it needs the hidden partition to be present locally.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from repere_suites.sta_lta import (  # noqa: E402
    STALTAFetchCodeSuite,
    STALTAIntentExtractionSuite,
    STALTAReportSuite,
    STALTATriggerCodeSuite,
)
from repere_suites.sta_lta.items import (  # noqa: E402
    PRIVATE_DIR,
    VALID_SPLITS,
    _load_events,
)


SUITE_FACTORIES: dict[str, type] = {
    "sta_lta.intent_extraction": STALTAIntentExtractionSuite,
    "sta_lta.fetch_code": STALTAFetchCodeSuite,
    "sta_lta.trigger_code": STALTATriggerCodeSuite,
    "sta_lta.report": STALTAReportSuite,
}


def _coerce_gold(gold) -> object:
    """Best-effort serialisation of gold values."""
    try:
        json.dumps(gold)
        return gold
    except TypeError:
        return repr(gold)


def dump_suite(suite_id: str, suite, *, split: str, out_path: Path) -> Path:
    """Dump a single (suite, split) pair as JSON.

    Each item carries `metadata` (event_id, cutoff_date) so reviewers and
    drift tests don't need to parse the prompt string to recover
    per-event provenance.
    """
    events = _load_events(split=split)
    suite_items = list(suite.items())
    if len(events) != len(suite_items):
        raise RuntimeError(
            f"{suite_id}/{split}: {len(events)} events but {len(suite_items)} suite items"
        )
    items = []
    for idx, (ev, (prompt, gold, _scorer)) in enumerate(zip(events, suite_items)):
        items.append({
            "item_index": idx,
            "metadata": {
                "event_id": ev["id"],
                "cutoff_date": ev["cutoff_date"],
            },
            "prompt": prompt,
            "gold": _coerce_gold(gold),
        })
    payload = {
        "schema_version": "0.3",
        "suite_id": suite_id,
        "split": split,
        "n_items": len(items),
        "items": items,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=REPO / "tests" / "fixtures",
        type=Path,
    )
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Only dump these suite ids",
    )
    parser.add_argument(
        "--splits",
        nargs="*",
        default=["validation"],
        choices=list(VALID_SPLITS),
        help="Splits to dump; default: validation. `test` writes to "
             "REPERE_EVAL_DATA_DIR, never to tests/fixtures/, because a "
             "test-split fixture carries the held-out gold.",
    )
    args = parser.parse_args(argv)

    suite_ids = args.only or list(SUITE_FACTORIES)
    written: list[Path] = []
    for sid in suite_ids:
        if sid not in SUITE_FACTORIES:
            print(f"WARN: unknown suite id {sid!r}; skipping", file=sys.stderr)
            continue
        for split in args.splits:
            suite = SUITE_FACTORIES[sid](split=split)
            # The held-out fixtures follow the held-out events out of the repo.
            out_dir = (PRIVATE_DIR / "fixtures") if split == "test" else args.output_dir
            out = out_dir / f"{sid}.{split}.json"
            dump_suite(sid, suite, split=split, out_path=out)
            written.append(out)
            print(f"Wrote {out}")
    print(f"\n{len(written)} fixtures written to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
