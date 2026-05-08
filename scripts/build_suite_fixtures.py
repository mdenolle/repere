"""Dump {prompt, gold} pairs for the four parametric STA/LTA suites.

The plot suite is excluded — its gold is a PNG file, handled by
scripts/build_plot_goldens.py. The other four suites are parametric over
events.yaml. Dumping their (prompt, gold) pairs lets reviewers see what the
benchmark actually asks for without running Python, and lets a drift test
catch unintended changes to either the prompt template or the gold construction.

Outputs:
    tests/fixtures/sta_lta.intent_extraction.json
    tests/fixtures/sta_lta.fetch_code.json
    tests/fixtures/sta_lta.trigger_code.json
    tests/fixtures/sta_lta.report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from frugalmind_suites.sta_lta import (  # noqa: E402
    STALTAFetchCodeSuite,
    STALTAIntentExtractionSuite,
    STALTAReportSuite,
    STALTATriggerCodeSuite,
)


SUITES: dict[str, object] = {
    "sta_lta.intent_extraction": STALTAIntentExtractionSuite(),
    "sta_lta.fetch_code": STALTAFetchCodeSuite(),
    "sta_lta.trigger_code": STALTATriggerCodeSuite(),
    "sta_lta.report": STALTAReportSuite(),
}


def _coerce_gold(gold) -> object:
    """Best-effort serialisation of gold values."""
    try:
        json.dumps(gold)
        return gold
    except TypeError:
        return repr(gold)


def dump_suite(suite_id: str, suite, out_path: Path) -> Path:
    items = []
    for idx, (prompt, gold, _scorer) in enumerate(suite.items()):
        items.append({
            "item_index": idx,
            "prompt": prompt,
            "gold": _coerce_gold(gold),
        })
    payload = {
        "schema_version": "0.1",
        "suite_id": suite_id,
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
    args = parser.parse_args(argv)

    suite_ids = args.only or list(SUITES)
    written: list[Path] = []
    for sid in suite_ids:
        if sid not in SUITES:
            print(f"WARN: unknown suite id {sid!r}; skipping", file=sys.stderr)
            continue
        out = args.output_dir / f"{sid}.json"
        dump_suite(sid, SUITES[sid], out)
        written.append(out)
        print(f"Wrote {out}")
    print(f"\n{len(written)} fixtures written to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
