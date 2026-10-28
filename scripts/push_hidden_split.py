#!/usr/bin/env python
"""Back up the held-out splits in $REPERE_EVAL_DATA_DIR to the PRIVATE Hub repo.

    uv run --with huggingface_hub python scripts/push_hidden_split.py          # dry run
    uv run --with huggingface_hub python scripts/push_hidden_split.py --yes    # upload

The counterpart of scripts/pull_eval_data.py. Uploads exactly the files listed
in that script's HIDDEN_FILES (the secret seed, the test-split YAML files and
the sta_lta test fixtures) to gaia-hazlab/repere-hidden, creating it as a
private dataset if needed. It refuses to run if the repository is, or would
be, public. Pulled caches (atlas/) are never uploaded.

Never generate a DOI for this repository: a DOI locks deletion and visibility,
and held-out partitions must stay rotatable (docs/holdout_policy.md).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pull_eval_data import HF_REPO, HIDDEN_FILES, PRIVATE_DIR  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=HF_REPO)
    ap.add_argument("--src", type=Path, default=PRIVATE_DIR)
    ap.add_argument("--yes", action="store_true", help="actually upload (default: dry run)")
    args = ap.parse_args()

    missing = [f for f in HIDDEN_FILES if not (args.src / f).exists()]
    if missing:
        print(f"error: missing in {args.src}: {missing}", file=sys.stderr)
        return 1
    print(f"{args.repo} (private) <- {args.src}")
    for f in HIDDEN_FILES:
        digest = hashlib.sha256((args.src / f).read_bytes()).hexdigest()[:12]
        print(f"  {f}  sha256={digest}")
    if not args.yes:
        print("dry run; pass --yes to upload")
        return 0

    from huggingface_hub import CommitOperationAdd, HfApi

    api = HfApi()
    api.create_repo(args.repo, repo_type="dataset", private=True, exist_ok=True)
    if not api.dataset_info(args.repo).private:
        print(f"error: {args.repo} is public; refusing to upload held-out data", file=sys.stderr)
        return 1
    ops = [CommitOperationAdd(path_in_repo=f, path_or_fileobj=str(args.src / f)) for f in HIDDEN_FILES]
    commit = api.create_commit(
        args.repo, repo_type="dataset", operations=ops, commit_message="Back up held-out splits"
    )
    print(f"uploaded revision {commit.oid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
