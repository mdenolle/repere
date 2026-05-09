"""Standard exporter for benchmark suites: one JSONL row per `(prompt, gold)` pair.

This module is the **canonical artifact format** for every FrugalMind suite.
Future suites (geobench, ASTRO/CLIM/QMECH, etc.) inherit the same schema so
they can ship to Hugging Face and external leaderboards without per-suite
serialization code.

Schema (one JSON object per JSONL line)
---------------------------------------

::

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
      "metadata":     {...}
    }

A sidecar ``manifest.json`` records the sha256 of every JSONL file so a
leaderboard row can be pinned to a specific dataset version.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "frugalmind.suite.v1"


@dataclass(frozen=True)
class BenchmarkRow:
    """One curated `(prompt, gold)` pair plus everything a scorer needs.

    Suites build these in their ``export_rows()`` method. The exporter
    serializes them to JSONL and records the file hash in a manifest so
    downstream consumers (HF datasets, external leaderboards) can pin a
    specific version.
    """

    id: str
    dataset_id: str
    suite_id: str
    version: str
    task_kind: str
    split: str
    visibility: str
    prompt: str
    gold: Any
    scorer_spec: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), sort_keys=False, ensure_ascii=False)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def export_suite(
    suite: Any,
    *,
    out_dir: Path,
    version: str | None = None,
) -> Path:
    """Write a single suite's curated rows to ``<out_dir>/<dataset>/<version>/<suite>.jsonl``.

    The suite must implement ``export_rows()`` returning an iterable of
    :class:`BenchmarkRow`. ``dataset_id``, ``suite_id`` and ``version`` are
    read from the suite (or overridden by the kwarg) so the file path is
    fully determined by the suite itself.
    """
    rows = list(suite.export_rows())
    if not rows:
        raise ValueError(f"Suite {type(suite).__name__} returned 0 rows; nothing to export")

    dataset_id = rows[0].dataset_id
    suite_id = rows[0].suite_id
    ver = version or rows[0].version

    target_dir = Path(out_dir) / dataset_id / ver
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{suite_id}.jsonl"

    with open(target, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(row.to_jsonl() + "\n")
    return target


def export_suites(
    suites: Iterable[Any],
    *,
    out_dir: Path,
    version: str | None = None,
) -> dict[str, Any]:
    """Export multiple suites and write a ``manifest.json`` with sha256 hashes.

    Returns the manifest dict. The manifest groups files by ``dataset_id`` so
    one call can export an entire benchmark family at once.
    """
    out_dir = Path(out_dir)
    written: list[dict[str, Any]] = []

    for suite in suites:
        path = export_suite(suite, out_dir=out_dir, version=version)
        n_rows = sum(1 for _ in open(path, encoding="utf-8"))
        written.append(
            {
                "dataset_id": suite.dataset_id,
                "suite_id": suite.suite_id,
                "version": version or suite.version,
                "task_kind": getattr(suite.task_kind, "value", str(suite.task_kind)),
                "path": str(path.relative_to(out_dir)),
                "rows": n_rows,
                "sha256": _sha256_file(path),
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "files": written,
    }

    # One manifest per dataset/version directory.
    by_dir: dict[Path, list[dict[str, Any]]] = {}
    for entry in written:
        d = out_dir / entry["dataset_id"] / entry["version"]
        by_dir.setdefault(d, []).append(entry)
    for d, entries in by_dir.items():
        m = {
            "schema_version": SCHEMA_VERSION,
            "dataset_id": entries[0]["dataset_id"],
            "version": entries[0]["version"],
            "generated_at": _utc_now_iso(),
            "files": entries,
        }
        (d / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")

    return manifest
