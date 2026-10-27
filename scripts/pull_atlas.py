"""Pull the RCA Atlas golden data sets at the commit pinned in Repère.

RCA Atlas owns these items; Repère only evaluates on them. Files land in
``$REPERE_EVAL_DATA_DIR/atlas/<commit>/`` (default ``data/private/``, which is
gitignored) and each is checked against its SHA-256 in
``src/repere_suites/atlas/pins.yaml`` before it is written.

Usage
-----
    pixi run python scripts/pull_atlas.py                 # every pinned file
    pixi run python scripts/pull_atlas.py agent_tasks     # one dataset
    pixi run python scripts/pull_atlas.py --check         # report, no download
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repere_suites.atlas import AtlasHashMismatch, cache_dir, fetch_atlas, load_pins


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="dataset names from pins.yaml (default: all)")
    ap.add_argument("--check", action="store_true", help="only report what is present and verified")
    ap.add_argument("--force", action="store_true", help="download even when a verified copy exists")
    args = ap.parse_args()

    pins = load_pins()
    out = cache_dir(pins)
    print(f"{pins['repo']} @ {pins['commit'][:7]} -> {out}")

    if args.check:
        from repere_suites.atlas import load_atlas

        missing = 0
        for name in args.names or pins["files"]:
            try:
                n = len(load_atlas(name, pins=pins))
                print(f"  ok       {name:16} {n} rows")
            except (FileNotFoundError, AtlasHashMismatch, ValueError) as exc:
                missing += 1
                print(f"  MISSING  {name:16} {exc}")
        return 1 if missing else 0

    try:
        written = fetch_atlas(args.names or None, pins=pins, force=args.force)
    except AtlasHashMismatch as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    for name, path in written.items():
        print(f"  verified {name:16} {Path(path).name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
