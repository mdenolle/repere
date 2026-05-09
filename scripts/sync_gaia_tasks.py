"""sync_gaia_tasks.py — Sync gaia-agentic-ai issues to the GAIA suite tasks.yaml.

Source of truth: GitHub issues labeled ``golden-task`` in
``uw-ssec/gaia-agentic-ai`` (see ``provenance.yaml`` in the suite directory).
Output:          ``src/frugalmind_suites/gaia_data_downloader/tasks.yaml``
                 (and the private partition under ``$FM_GAIA_GOLDEN_DIR``).

Modes
-----
  --bootstrap-from <yaml>    Open one issue per task in the YAML, on the
                             upstream repo. Used once to seed the 30 starter
                             issues from this committed tasks.yaml.
  --release vX.Y.Z           Pull all verified/frozen issues, render YAML,
                             hash, write.
  --dry-run                  Print what would happen; no GitHub or file writes.

Cross-repo flow
---------------
This script lives in ``frugalmind`` but reads from ``uw-ssec/gaia-agentic-ai``.
Both repos use the ``gh`` CLI, so the script needs ``gh auth status`` to
report a token with ``repo`` scope on both repos.

This is a STUB / OUTLINE — the real implementation needs:
  * ``pip install pydantic pyyaml`` for schema validation.
  * ``_render_issue_body()`` that round-trips through the
    ``.github/ISSUE_TEMPLATE/golden-task.yml`` form on the upstream repo.
  * Public/private partition split (records with visibility=='private' go to
    ``$FM_GAIA_GOLDEN_DIR``, NEVER to the public ``tasks.yaml``).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import yaml


UPSTREAM_REPO = "uw-ssec/gaia-agentic-ai"
SCHEMA_VERSION = "0.1"
SUITE_DIR = Path(__file__).resolve().parents[1] / "src" / "frugalmind_suites" / "gaia_data_downloader"
PUBLIC_TASKS_PATH = SUITE_DIR / "tasks.yaml"


@dataclass
class GoldenTask:
    id: str
    issue_url: str
    domain: str
    difficulty: str
    split: str
    visibility: str
    prompt: str
    expected_tools: list[str]
    required_cli_args: list[str]
    expected_files: list[dict[str, Any]]
    checksum_strategy: str
    data_source_url: str
    timeout_s: int
    contamination_risk: str
    cutoff_date: str | None = None
    notes: str | None = None


# --------------------------------------------------------------------------- #
# Issue parsing (upstream repo)
# --------------------------------------------------------------------------- #
def fetch_issues(label: str = "golden-task") -> list[dict]:
    cmd = [
        "gh", "issue", "list",
        "--repo", UPSTREAM_REPO,
        "--label", label,
        "--state", "all",
        "--limit", "500",
        "--json", "number,title,body,labels,url,state,createdAt,updatedAt",
    ]
    out = subprocess.check_output(cmd, text=True)
    return json.loads(out)


def issue_to_task(issue: dict) -> GoldenTask:
    """Parse a GitHub issue body (rendered from golden-task.yml form) into a task."""
    raise NotImplementedError(
        "TODO: implement form-field parsing. Use markdown-it-py to extract the "
        "value under each `### <Label>` heading that the issue form produces. "
        "See docs/sync_protocol.md for the round-trip schema."
    )


def _validate(task: GoldenTask) -> list[str]:
    errors: list[str] = []
    if not task.id.startswith("gaia-dl-"):
        errors.append(f"id must start with gaia-dl-: {task.id}")
    if task.domain not in {"seismic", "hydrology", "dem", "climate", "cross"}:
        errors.append(f"unknown domain: {task.domain}")
    if task.difficulty not in {"easy", "medium", "hard"}:
        errors.append(f"unknown difficulty: {task.difficulty}")
    if task.split not in {"validation", "test"}:
        errors.append(f"unknown split: {task.split}")
    if task.visibility not in {"public", "private"}:
        errors.append(f"unknown visibility: {task.visibility}")
    if task.contamination_risk == "high" and task.visibility != "private":
        errors.append(f"{task.id}: contamination_risk=high requires visibility=private")
    return errors


# --------------------------------------------------------------------------- #
# Bootstrap mode — open the initial 30 issues from a YAML on the upstream repo
# --------------------------------------------------------------------------- #
def _render_issue_body(t: dict) -> str:
    """Render a task dict into the body of a golden-task issue (markdown form)."""
    lines = [
        f"### Task ID\n\n{t['id']}\n",
        f"### Domain\n\n{t['domain']}\n",
        f"### Difficulty\n\n{t['difficulty']}\n",
        f"### Partition\n\n{t['visibility']}\n",
        f"### Agent prompt (user message)\n\n{t['prompt'].rstrip()}\n",
        f"### Expected tools (one per line)\n\n" + "\n".join(t["expected_tools"]) + "\n",
        f"### Required CLI args of the generated script (one per line)\n\n"
        + "\n".join(t["required_cli_args"]) + "\n",
        f"### Expected output files (one glob + count range per line)\n\n"
        + "\n".join(f"{f['glob']}  min={f['min']}  max={f['max']}" for f in t["expected_files"])
        + "\n",
        f"### Checksum strategy\n\n{t['checksum_strategy']}\n",
        f"### Data source URL\n\n{t['data_source_url']}\n",
        f"### Sandbox timeout (seconds)\n\n{t['timeout_s']}\n",
        f"### Contamination risk\n\n{t['contamination_risk']}\n",
        f"### Notes / rationale (optional)\n\n{t.get('notes', '')}\n",
    ]
    return "\n".join(lines)


def bootstrap_from_yaml(yaml_path: Path, dry_run: bool) -> None:
    data = yaml.safe_load(yaml_path.read_text())
    tasks = data["tasks"]
    print(f"Will open {len(tasks)} issues on {UPSTREAM_REPO}", file=sys.stderr)
    for t in tasks:
        title = f"[golden-task]: {t['id']} — {t['domain']}/{t['difficulty']}"
        body = _render_issue_body(t)
        labels = [
            "golden-task",
            f"domain:{t['domain']}",
            f"difficulty:{t['difficulty']}",
            f"partition:{t['visibility']}",
            "status:draft",
        ]
        cmd = [
            "gh", "issue", "create",
            "--repo", UPSTREAM_REPO,
            "--title", title,
            "--body", body,
            *(arg for label in labels for arg in ("--label", label)),
        ]
        if dry_run:
            print(" ".join(cmd))
        else:
            subprocess.run(cmd, check=True)


# --------------------------------------------------------------------------- #
# Release mode — issues -> tasks.yaml
# --------------------------------------------------------------------------- #
def emit_release(release: str, dry_run: bool) -> None:
    issues = fetch_issues()
    public: list[dict] = []
    private: list[dict] = []
    errors: list[str] = []

    for issue in issues:
        try:
            task = issue_to_task(issue)
        except NotImplementedError as e:
            print(f"SKIP issue #{issue['number']}: {e}", file=sys.stderr)
            continue
        ve = _validate(task)
        if ve:
            errors.extend(f"#{issue['number']}: {e}" for e in ve)
            continue
        bucket = private if task.visibility == "private" else public
        bucket.append(asdict(task))

    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)

    public.sort(key=lambda t: t["id"])
    private.sort(key=lambda t: t["id"])

    public_blob = yaml.safe_dump(
        {"schema_version": float(SCHEMA_VERSION), "tasks": public},
        sort_keys=False,
    )
    private_dir = Path(os.environ.get("FM_GAIA_GOLDEN_DIR", "/tmp/fm_gaia_private"))
    private_path = private_dir / f"tasks.{release}.private.yaml"
    sha_path = SUITE_DIR / f"tasks.{release}.sha256"

    if dry_run:
        print(f"Would write {len(public)} public tasks to {PUBLIC_TASKS_PATH}")
        print(f"Would write {len(private)} private tasks to {private_path}")
        return

    PUBLIC_TASKS_PATH.write_text(public_blob)
    private_dir.mkdir(parents=True, exist_ok=True)
    private_path.write_text(yaml.safe_dump({"tasks": private}, sort_keys=False))
    sha_path.write_text(
        f"{hashlib.sha256(public_blob.encode()).hexdigest()}  tasks.yaml\n"
    )
    print(f"Wrote {PUBLIC_TASKS_PATH} ({len(public)} public tasks)")
    print(f"Wrote {private_path} ({len(private)} private tasks; gitignored)")
    print(f"Wrote {sha_path}")


# --------------------------------------------------------------------------- #
def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bootstrap-from", type=Path, help="YAML of seed tasks; open issues from each")
    p.add_argument("--release", type=str, help="Release tag to emit, e.g. v0.1.0")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.bootstrap_from:
        bootstrap_from_yaml(args.bootstrap_from, args.dry_run)
    elif args.release:
        emit_release(args.release, args.dry_run)
    else:
        p.error("must pass --bootstrap-from or --release")


if __name__ == "__main__":
    main()
