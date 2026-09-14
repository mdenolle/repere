"""FrugalMind RCA — evaluation suite for agents serving the OOI Regional Cabled Array.

Three agent families (coding, lit-review, sensor), seven task groups, four
verification tiers. Design: ``DESIGN.md`` at the repo root. Authoring rules:
``docs/rca/AUTHORING.md``. Open questions: ``OPEN_QUESTIONS.md``.

Layout::

    schema/golden_record.schema.json   record contract (shape A + shape B)
    seeds/<family>/*.yaml              template records (status: template)
    data/public/                       small public fixtures, sha256-pinned
    pricing/prices.yaml                frozen price map (versioned, dated)
    validate.py                        schema + cross-field rules (R01..R15)
    checkers.py                        T2 deterministic checkers
    cost.py                            cost layer over Inspect logs
    solvers.py                         scripted self-test solver
    inspect_tasks.py                   Inspect @task + tier-dispatching @scorer
    run.py                             CLI: records -> Inspect eval -> logged result

Everything here imports ``inspect_ai`` lazily except ``inspect_tasks`` and
``solvers``; the package stays importable with only PyYAML installed.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "schema" / "golden_record.schema.json"
SEEDS_DIR = HERE / "seeds"
PUBLIC_DATA_DIR = HERE / "data" / "public"
PRICES_PATH = HERE / "pricing" / "prices.yaml"

FAMILIES = ("coding", "litreview", "sensor")
TIERS = ("T1_physics", "T2_execution", "T3_reference", "T4_judgment")


def private_data_dir() -> Path | None:
    """Root of the private (hidden split) records and files, if configured."""
    v = os.environ.get("FM_RCA_PRIVATE_DIR")
    return Path(v) if v else None


def record_paths(
    *,
    roots: Iterable[Path] | None = None,
    family: str | None = None,
) -> list[Path]:
    """All record files under the seed roots (public) plus the private root when set."""
    if roots is None:
        roots = [SEEDS_DIR]
        priv = private_data_dir()
        if priv and (priv / "records").is_dir():
            roots.append(priv / "records")
    out: list[Path] = []
    for root in roots:
        if not Path(root).is_dir():
            continue
        for p in sorted(Path(root).rglob("*.y*ml")):
            if p.name.startswith("_"):
                continue
            if family and p.parent.name != family and f"/{family}/" not in str(p):
                continue
            out.append(p)
    return out


def load_records(
    *,
    ids: Iterable[str] | None = None,
    family: str | None = None,
    tier: str | None = None,
    split: str | None = None,
    include_templates: bool = True,
) -> list[dict[str, Any]]:
    """Load and filter records. Uses the validator's loader so dates are strings."""
    from .validate import load_record

    wanted = set(ids) if ids else None
    out: list[dict[str, Any]] = []
    for p in record_paths(family=family):
        rec = load_record(p)
        rec["_path"] = str(p)
        if wanted and rec.get("id") not in wanted:
            continue
        if tier and rec.get("tier") != tier:
            continue
        if split and (rec.get("holdout") or {}).get("split") != split:
            continue
        if not include_templates and rec.get("status") == "template":
            continue
        out.append(rec)
    return out


__all__ = [
    "FAMILIES",
    "HERE",
    "PRICES_PATH",
    "PUBLIC_DATA_DIR",
    "SCHEMA_PATH",
    "SEEDS_DIR",
    "TIERS",
    "load_records",
    "private_data_dir",
    "record_paths",
]
