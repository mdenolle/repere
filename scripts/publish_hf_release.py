#!/usr/bin/env python
"""Upload a built release folder to its public Hugging Face repository.

    pixi run -e full python scripts/build_hf_release.py codameter
    uv run --with huggingface_hub --with pyyaml python scripts/publish_hf_release.py codameter          # dry run
    uv run --with huggingface_hub --with pyyaml python scripts/publish_hf_release.py codameter --yes    # upload

Creates ``hf_repo`` from datasets/releases.yaml as a PUBLIC dataset if needed,
uploads the folder in one commit, tags the commit with the release version, and
prints the revision to record in releases.yaml (``hf_revision``).

Before uploading it re-checks the folder: every data row must be
split=validation and visibility=public, and every file must match manifest.json.
Generating the DOI is a separate, manual step in the repository settings on the
Hub; it locks the repository (no delete, rename or visibility change), so do it
only after reading the uploaded card.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent


def check_folder(folder: Path) -> list[str]:
    """Return problems that must block an upload (empty list = clean)."""
    problems = []
    manifest = json.loads((folder / "manifest.json").read_text())
    for f in manifest["files"]:
        p = folder / f["path"]
        if not p.exists():
            problems.append(f"missing {f['path']}")
            continue
        if hashlib.sha256(p.read_bytes()).hexdigest() != f["sha256"]:
            problems.append(f"sha256 mismatch {f['path']}")
    for p in sorted((folder / "data").glob("*.jsonl")):
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            row = json.loads(line)
            if row.get("split") != "validation" or row.get("visibility") != "public":
                problems.append(f"{p.name}:{n} is {row.get('split')}/{row.get('visibility')}")
    for name in ("croissant.json", "tasks.jsonld", "README.md"):
        if not (folder / name).exists():
            problems.append(f"missing {name}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("release")
    ap.add_argument("--folder", type=Path, default=None, help="built folder (default build/hf/<release>)")
    ap.add_argument("--yes", action="store_true", help="actually upload (default: dry run)")
    args = ap.parse_args()

    release = yaml.safe_load((REPO / "datasets" / "releases.yaml").read_text())["releases"][args.release]
    if release.get("status") != "release":
        print(f"error: {args.release} has status {release.get('status')!r}", file=sys.stderr)
        return 1
    folder = args.folder or REPO / "build" / "hf" / args.release
    problems = check_folder(folder)
    if problems:
        print("refusing to upload:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    files = sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file())
    print(f"{release['hf_repo']} (public) <- {folder}")
    for f in files:
        print(f"  {f}")
    if not args.yes:
        print("dry run; pass --yes to upload")
        return 0

    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(release["hf_repo"], repo_type="dataset", private=False, exist_ok=True)
    commit = api.upload_folder(
        repo_id=release["hf_repo"],
        repo_type="dataset",
        folder_path=str(folder),
        commit_message=f"Repère release {args.release} {release['version']}",
    )
    revision = commit.oid
    api.create_tag(release["hf_repo"], repo_type="dataset", tag=release["version"], revision=revision, exist_ok=True)
    print(f"uploaded revision {revision}, tagged {release['version']}")
    print(f"record in datasets/releases.yaml: hf_revision: {revision}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
