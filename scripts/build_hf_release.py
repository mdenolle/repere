#!/usr/bin/env python
"""Build a public Hugging Face release folder for one entry of datasets/releases.yaml.

    pixi run -e full python scripts/build_hf_release.py codameter --out build/hf/codameter
    pixi run -e full python scripts/build_hf_release.py synthetic_stalta --out build/hf/synthetic_stalta

The folder holds everything the Hub repository will contain:

    data/<suite_id>.jsonl   public development rows (BenchmarkRow schema)
    data/...                extra files named in the release (e.g. a seed waveform)
    manifest.json           sha256 and row count per file
    croissant.json          Croissant 1.1 + RAI (+ GeoCroissant when the release has `geo`)
    tasks.jsonld            Croissant Tasks: one TaskProblem per suite
    README.md               dataset card: license, citation, readiness profile

The build refuses any row that is not split=validation and visibility=public,
and it runs with REPERE_EVAL_DATA_DIR pointed at an empty directory so a hidden
split present on this machine cannot be merged into the export. Uploading is a
separate step (scripts/publish_hf_release.py), so the folder can be read first.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from importlib.metadata import version as pkg_version
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
RELEASES = REPO / "datasets" / "releases.yaml"

CREATOR = [
    {
        "@type": "Person",
        "name": "Marine Denolle",
        "affiliation": "University of Washington",
        "url": "https://github.com/mdenolle",
    }
]

READINESS_NAMES = {
    "A1": "Provenance & rights",
    "A2": "Physical comparability",
    "A3": "Quality & gaps",
    "A4": "Structure & metadata",
    "B1": "Diversity",
    "B7": "Independent partitioning",
    "D1": "Task specification",
    "D2": "Reference validity",
    "D3": "Contamination",
    "D4": "Task diversity",
    "D5": "Unanswerable cases",
    "D6": "Score stability",
}


class ReleaseError(RuntimeError):
    pass


def load_releases(path: Path = RELEASES) -> dict:
    return yaml.safe_load(path.read_text())["releases"]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_suite(spec: str):
    module, cls = spec.split(":")
    return getattr(importlib.import_module(module), cls)()


def assert_no_hidden_source(suite, empty_dir: str) -> None:
    """Refuse to export from a suite that can see a held-out split.

    The suites resolve their private directory when first imported, so the
    REPERE_EVAL_DATA_DIR override only helps if nothing imported them earlier;
    codameter loads a hidden corpus from CODAMETER_GOLDEN_DIR. Check both.
    """
    module = sys.modules[type(suite).__module__]
    private = getattr(module, "PRIVATE_DIR", None)
    if private is not None and Path(private).resolve() != Path(empty_dir).resolve():
        raise ReleaseError(f"{module.__name__}.PRIVATE_DIR is {private}, not an empty directory")
    if "codameter" in sys.modules or type(suite).__module__.startswith("repere_suites.dvv"):
        try:
            from codameter import golden
        except ImportError:
            return
        if golden.IS_HIDDEN_SET:
            raise ReleaseError(f"codameter loaded a hidden corpus from {golden.DATA_DIR}")


@contextlib.contextmanager
def isolated_from_private(module, empty_dir: str):
    """Point a suite module's private paths at an empty directory, then restore.

    Suites resolve PRIVATE_DIR (and paths under it, such as a hidden-cases file)
    when first imported, so an environment override is too late if anything
    imported them earlier in the process. Rebase every module-level Path under
    the old PRIVATE_DIR for the duration of the export.
    """
    old_dir = getattr(module, "PRIVATE_DIR", None)
    if old_dir is None:
        yield
        return
    old_dir = Path(old_dir)
    saved = {}
    for name, value in vars(module).items():
        if isinstance(value, Path) and (value == old_dir or old_dir in value.parents):
            saved[name] = value
    try:
        for name, value in saved.items():
            setattr(module, name, Path(empty_dir) / value.relative_to(old_dir))
        yield
    finally:
        for name, value in saved.items():
            setattr(module, name, value)


def public_rows(suite) -> list:
    """The suite's released rows. Raises if any row is held out."""
    rows = [r for r in suite.export_rows() if r.split == "validation"]
    bad = [r.id for r in rows if r.visibility != "public"]
    if bad:
        raise ReleaseError(f"validation rows not marked public: {bad}")
    if not rows:
        raise ReleaseError(f"{type(suite).__name__} has no public validation rows")
    return rows


def _cite_as(release: dict, url: str, year: int) -> str:
    key = release["hf_repo"].split("/")[-1].replace("-", "_") + f"_{year}"
    doi = release.get("doi")
    lines = [
        f"@misc{{{key},",
        "  author = {Denolle, Marine},",
        f"  title = {{{release['pretty_name']}}},",
        f"  year = {{{year}}},",
        "  publisher = {Hugging Face},",
        f"  version = {{{release['version']}}},",
        f"  url = {{{url}}},",
    ]
    if doi:
        lines.append(f"  doi = {{{doi}}},")
    lines.append("}")
    return "\n".join(lines)


def _card(release: dict, files: list[dict], suites: list[dict], cite_as: str) -> str:
    rows_by_suite = {f["suite_id"]: f["rows"] for f in files if f.get("suite_id")}
    front = {
        "license": release["license"],
        "pretty_name": release["pretty_name"],
        "language": ["en"],
        "tags": ["croissant", "benchmark", "agent-evaluation", "geoscience", "repere"],
        "size_categories": ["n<1K"],
        "configs": [
            {
                "config_name": s["suite_id"],
                "data_files": [{"split": "validation", "path": f"data/{s['suite_id']}.jsonl"}],
            }
            for s in suites
        ],
    }
    if release.get("license_name"):
        front["license_name"] = release["license_name"]
        front["license_link"] = "LICENSE.md"
    out = ["---", yaml.safe_dump(front, sort_keys=False).rstrip(), "---", ""]
    out += [f"# {release['pretty_name']}", ""]
    if release.get("doi"):
        out += [f"DOI: [{release['doi']}](https://doi.org/{release['doi']})", ""]
    out += [" ".join(release["description"].split()), ""]
    out += [
        "Part of [Repère](https://github.com/mdenolle/repere), an open benchmark for AI "
        "agents in the geosciences. Rows follow Repère's `BenchmarkRow` schema; rebuild "
        "a row's scorer with `make_scorer_from_spec(row['scorer_spec'])` from the suite "
        "named in the table below.",
        "",
        "## Contents",
        "",
        "| Config | Rows | Task kind | Model must return |",
        "|---|---|---|---|",
    ]
    for s in suites:
        out.append(
            f"| `{s['suite_id']}` | {rows_by_suite[s['suite_id']]} | {s['task_kind']} | "
            f"{' '.join(s['output'].split())} |"
        )
    out += ["", "**Scoring.**", ""]
    for s in suites:
        out.append(f"- `{s['suite_id']}`: {' '.join(s['evaluation'].split())}")
    out += [
        "",
        "Only the public development split (`validation`) is released. The evaluation "
        "split is withheld so that ranked scores measure capability rather than recall; "
        "scores on this split are for development and are not rankings.",
        "",
        "```python",
        "from datasets import load_dataset",
        f"ds = load_dataset(\"{release['hf_repo']}\", \"{suites[0]['suite_id']}\", split=\"validation\")",
        "```",
        "",
        "## Metadata",
        "",
        "- `croissant.json`: Croissant 1.1 with the Responsible AI extension"
        + (" and GeoCroissant 1.0 (station location, time span, sampling)." if release.get("geo") else "."),
        "- `tasks.jsonld`: one Croissant Tasks `TaskProblem` per config (input, output, "
        "implementation, execution and evaluation specs). Croissant Tasks is experimental upstream.",
        "- `manifest.json`: sha256 and row count of every file. A Repère score names the "
        "manifest it was computed on.",
        "",
    ]
    dep = release.get("depends_on")
    if dep:
        out += [
            "## Dependency",
            "",
            f"Scoring regenerates each case's data with [{dep['name']}]({dep['url']}) "
            f"{dep['version']}, commit `{dep['commit']}`. Install that commit to reproduce scores.",
            "",
        ]
    out += ["## License", "", f"`{release['license']}`" + (f" ({release['license_name']})" if release.get("license_name") else "") + "."]
    if release.get("license_note"):
        out += ["", " ".join(release["license_note"].split())]
    out += [""]
    if release.get("cite_also"):
        out += ["Cite the source data:", ""] + [f"- {c}" for c in release["cite_also"]] + [""]
    out += ["## Readiness profile (v0 self-assessment, not reviewed)", ""]
    out += [
        "Evidence level: 0 missing, 1 present but incomplete, 2 verifiable by another "
        "team, n/a not yet assessed. Criteria follow the AI-readiness instrument "
        "(A analysis readiness, B AI readiness, D agent-evaluation datasets). Levels "
        "are never summed.",
        "",
        "| ID | Criterion | Level | Evidence |",
        "|---|---|---|---|",
    ]
    for cid, entry in release.get("readiness", {}).items():
        lvl = entry.get("level")
        out.append(
            f"| {cid} | {READINESS_NAMES.get(cid, cid)} | {'n/a' if lvl is None else lvl} | "
            f"{entry.get('evidence', '')} |"
        )
    out += ["", "## Responsible AI", ""]
    for k, v in (release.get("rai") or {}).items():
        text = ", ".join(v) if isinstance(v, list) else " ".join(str(v).split())
        out.append(f"- **{k}**: {text}")
    out += ["", "## Citation", "", "```bibtex", cite_as, "```", ""]
    return "\n".join(out)


def _license_file(release: dict) -> str:
    """Mixed-terms licence file: Repère's MIT text plus the source-data terms."""
    parts = [
        f"# License: {release['license_name']}",
        "",
        " ".join(release["license_note"].split()),
        "",
    ]
    if release.get("cite_also"):
        parts += ["Source data citations:", ""] + [f"- {c}" for c in release["cite_also"]] + [""]
    parts += ["## MIT License (Repère content)", "", "```", (REPO / "LICENSE").read_text().strip(), "```", ""]
    return "\n".join(parts)


def build(name: str, out: Path, *, base_url: str | None = None) -> dict:
    releases = load_releases()
    if name not in releases:
        raise ReleaseError(f"unknown release {name!r}; known: {sorted(releases)}")
    release = releases[name]
    if release.get("status") != "release":
        raise ReleaseError(f"release {name!r} has status {release.get('status')!r}; nothing to build")

    url = f"https://huggingface.co/datasets/{release['hf_repo']}"
    if base_url is None:
        base_url = f"{url}/resolve/main/"

    if out.exists():
        shutil.rmtree(out)
    (out / "data").mkdir(parents=True)

    files: list[dict] = []
    suites: list[dict] = []
    with tempfile.TemporaryDirectory() as empty:
        old = os.environ.get("REPERE_EVAL_DATA_DIR")
        os.environ["REPERE_EVAL_DATA_DIR"] = empty
        os.environ.pop("CODAMETER_GOLDEN_DIR", None)
        try:
            for entry in release["suites"]:
                suite = _load_suite(entry["cls"])
                module = sys.modules[type(suite).__module__]
                with isolated_from_private(module, empty):
                    assert_no_hidden_source(suite, empty)
                    rows = public_rows(suite)
                path = out / "data" / f"{suite.suite_id}.jsonl"
                path.write_text("".join(r.to_jsonl() + "\n" for r in rows), encoding="utf-8")
                task_kind = getattr(suite.task_kind, "value", str(suite.task_kind))
                files.append(
                    {
                        "path": f"data/{suite.suite_id}.jsonl",
                        "suite_id": suite.suite_id,
                        "rows": len(rows),
                        "rows_data": [json.loads(r.to_jsonl()) for r in rows],
                        "encoding": "application/jsonlines",
                        "description": f"Public development rows for {suite.suite_id} (BenchmarkRow JSONL).",
                    }
                )
                suites.append(
                    {
                        "suite_id": suite.suite_id,
                        "task_kind": task_kind,
                        "scorer": rows[0].scorer_spec["name"],
                        "output": entry["output"],
                        "evaluation": entry["evaluation"],
                    }
                )
        finally:
            if old is None:
                os.environ.pop("REPERE_EVAL_DATA_DIR", None)
            else:
                os.environ["REPERE_EVAL_DATA_DIR"] = old

    for extra in release.get("extra_files", []):
        dest = out / extra["to"]
        shutil.copyfile(REPO / extra["from"], dest)
        files.append(
            {
                "path": extra["to"],
                "encoding": extra["encoding"],
                "description": " ".join(extra["description"].split()),
            }
        )
    for f in files:
        f["sha256"] = _sha256(out / f["path"])

    now = datetime.now(timezone.utc)
    manifest = {
        "schema_version": "repere.release.v1",
        "release": name,
        "hf_repo": release["hf_repo"],
        "version": release["version"],
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repere_version": pkg_version("repere"),
        "files": [{k: f[k] for k in ("path", "sha256") if k in f} | ({"rows": f["rows"]} if "rows" in f else {}) for f in files],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    from repere.croissant import dataset_metadata, task_problems

    cite_as = _cite_as(release, url, now.year)
    md = dataset_metadata(
        release,
        files,
        url=url,
        base_url=base_url,
        cite_as=cite_as,
        date_published=now.strftime("%Y-%m-%d"),
        creator=CREATOR,
    )
    (out / "croissant.json").write_text(json.dumps(md, indent=2, ensure_ascii=False) + "\n")
    tasks = task_problems(release, suites, url=url, repere_version=pkg_version("repere"))
    (out / "tasks.jsonld").write_text(json.dumps(tasks, indent=2, ensure_ascii=False) + "\n")
    (out / "README.md").write_text(_card(release, files, suites, cite_as))
    if release.get("license_name"):
        (out / "LICENSE.md").write_text(_license_file(release))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("release", help="entry name in datasets/releases.yaml")
    ap.add_argument("--out", type=Path, default=None, help="output folder (default build/hf/<release>)")
    ap.add_argument(
        "--base-url",
        default=None,
        help="prefix for contentUrl in croissant.json (default: the Hub resolve URL; '' for relative paths)",
    )
    args = ap.parse_args()
    out = args.out or REPO / "build" / "hf" / args.release
    try:
        manifest = build(args.release, out, base_url=args.base_url)
    except ReleaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for f in manifest["files"]:
        print(f"{f['path']:40s} rows={f.get('rows', '-'):>4}  sha256={f['sha256'][:12]}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
