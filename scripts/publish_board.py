#!/usr/bin/env python
"""Build, check and publish the public board from a private run host.

Run this on the GPU host after an eval sweep. It reads the run outputs, builds
schema-v0.2 rows, attaches a provenance block, refuses to write anything that
fails the outbound guard, and optionally commits and pushes.

    pixi run -e default python scripts/publish_board.py \\
        --results-dir results --host-label "ess-gpu-01" --epochs 5

    # and, once the guard has been watched to pass a few times:
    ... --commit --push

The guard is the reason this script exists rather than a shell one-liner. A host
that pushes to git without a human in the loop needs something between the run
output and the public page, and ``repere.publish`` is that something: an
allowlist of row fields, a refusal of any free text, and a check for held-out
vocabulary anywhere in the payload.

Nothing is written when the check fails, so a failed publish cannot leave a
half-written file for a later commit to pick up.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from repere.leaderboard import build_leaderboard, load_eval_results  # noqa: E402
from repere.provenance import capture_run_provenance  # noqa: E402
from repere.publish import PublishError, write_board  # noqa: E402


def _git(*args: str) -> str:
    out = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{out.stderr.strip()}")
    return out.stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results-dir", type=Path, default=REPO_ROOT / "results")
    ap.add_argument("--output", type=Path, default=REPO_ROOT / "site" / "data" / "leaderboard.json")
    ap.add_argument("--host-label", default=None, help="human name for this machine")
    ap.add_argument("--epochs", type=int, default=None, help="repeats per configuration")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--commit", action="store_true", help="git commit the board")
    ap.add_argument("--push", action="store_true", help="git push (implies --commit)")
    ap.add_argument(
        "--allow-warnings",
        action="store_true",
        help="publish even when the guard reports advisory warnings",
    )
    args = ap.parse_args()

    results = load_eval_results(args.results_dir)
    if not results:
        raise SystemExit(f"no result files in {args.results_dir}")

    provenance = capture_run_provenance(
        repo_root=REPO_ROOT,
        model_ids=sorted({str(r.get("model_id")) for r in results if r.get("model_id")}),
        host_label=args.host_label,
        seed=args.seed,
        temperature=args.temperature,
        n_epochs=args.epochs,
    )

    payload = build_leaderboard(results, source=str(args.results_dir))
    payload["provenance"] = provenance.to_payload()
    payload["provenance"]["warnings"] = provenance.warnings()

    # Stamp the host on every row so the renderer can refuse to compare
    # latency, energy or resource consistency across machines.
    for row in payload["leaderboard"]:
        row["host_id"] = provenance.host.host_id

    try:
        warnings = write_board(payload, args.output)
    except PublishError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    print(f"wrote {args.output} ({len(payload['leaderboard'])} rows)")
    print(f"host {provenance.host.host_id} — {provenance.host.gpu_summary}")
    if warnings:
        print("\nwarnings:")
        for w in warnings:
            print(f"  - {w}")
        if not (args.commit or args.push):
            pass
        elif not args.allow_warnings:
            print(
                "\nnot committing: rerun with --allow-warnings to publish anyway",
                file=sys.stderr,
            )
            return 1

    if args.commit or args.push:
        rel = args.output.relative_to(REPO_ROOT)
        _git("add", str(rel))
        if not _git("diff", "--cached", "--name-only"):
            print("no change to commit")
            return 0
        label = args.host_label or provenance.host.host_id
        _git("commit", "-m", f"board: refresh from {label} ({provenance.harness_commit or '?'})")
        print("committed")
        if args.push:
            _git("push")
            print("pushed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
