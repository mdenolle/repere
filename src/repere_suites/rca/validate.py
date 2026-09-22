"""Validate RCA golden records against the schema and the cross-field rules.

Usage::

    python -m repere_suites.rca.validate                # all seeds
    python -m repere_suites.rca.validate path/to/dir     # a directory
    python -m repere_suites.rca.validate a.yaml b.yaml   # files
    python -m repere_suites.rca.validate --strict        # templates fail

Exit status 0 when every record passes, 1 otherwise. Prints one line per
problem as ``<file>: <rule>: <message>``.

Two layers of checks:

1. **Schema** (``schema/golden_record.schema.json``, JSON Schema 2020-12) via
   the ``jsonschema`` package when it is importable. Without it, a reduced
   structural check runs (required keys, enums) and a warning is printed so
   nobody mistakes the reduced check for the full one.
2. **Cross-field rules** the schema cannot express. Each has a stable id
   (``R01`` ...) so authoring guidelines and CI messages can cite them.

The rules are the contract for co-authors; see ``docs/rca/AUTHORING.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "schema" / "golden_record.schema.json"
SEEDS_DIR = HERE / "seeds"
PUBLIC_DATA_DIR = HERE / "data" / "public"
EXTERNAL_DATA_DIR = HERE / "data" / "external"

# Placeholder DOI prefix used by the lit_rag seed corpus; never valid here.
_FAKE_DOI_PREFIXES = ("10.0000/",)

_FAMILY_GROUPS = {
    "coding": {"1a_download_processing", "1b_qc", "1c_calibration_timing", "1d_coding_tools"},
    "litreview": {"2_litreview"},
    "sensor": {"3_sensor"},
}

_TIER_METHODS = {
    "T1_physics": {"oracle_compare"},
    "T2_execution": {"execution_check"},
    "T3_reference": {"retrieval_metrics", "citation_support", "exact_match"},
    "T4_judgment": {"rubric_judge"},
}

_SHAPE_B_REQUIRED = ("tools", "inputs", "task", "sandbox")
_SHAPE_A_FORBIDDEN = ("tools", "inputs", "task", "sandbox")


def _coerce_dates(obj: Any) -> Any:
    """PyYAML turns bare ``2026-09-14`` into ``datetime.date``; the schema wants
    ISO strings. Coerce recursively so YAML and JSON records validate alike."""
    import datetime as _dt

    if isinstance(obj, dict):
        return {k: _coerce_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_coerce_dates(v) for v in obj]
    if isinstance(obj, (_dt.date, _dt.datetime)):
        return obj.isoformat()
    return obj


def load_record(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        if path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(fh)
        else:
            data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    return _coerce_dates(data)


def _iter_paths(args: list[str]) -> Iterable[Path]:
    if not args:
        args = [str(SEEDS_DIR)]
    for a in args:
        p = Path(a)
        if p.is_dir():
            yield from sorted(q for q in p.rglob("*") if q.suffix in (".yaml", ".yml", ".json"))
        else:
            yield p


# ---------------------------------------------------------------------------
# Layer 1: schema
# ---------------------------------------------------------------------------


def schema_errors(record: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    try:
        import jsonschema
    except ImportError:
        return _reduced_schema_check(record, schema)
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    out = []
    for err in sorted(validator.iter_errors(record), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "<root>"
        out.append(f"schema: {loc}: {err.message}")
    return out


_REDUCED_WARNED = False


def _reduced_schema_check(record: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    global _REDUCED_WARNED
    if not _REDUCED_WARNED:
        print(
            "WARNING: jsonschema not installed; running the reduced structural check only. "
            "pip install jsonschema for the full validation.",
            file=sys.stderr,
        )
        _REDUCED_WARNED = True
    out = []
    for key in schema.get("required", []):
        if key not in record:
            out.append(f"schema(reduced): missing required key {key!r}")
    props = schema.get("properties", {})
    for key, val in record.items():
        if key not in props:
            out.append(f"schema(reduced): unknown top-level key {key!r}")
            continue
        enum = props[key].get("enum")
        if enum is not None and val not in enum:
            out.append(f"schema(reduced): {key}={val!r} not in {enum}")
    return out


# ---------------------------------------------------------------------------
# Layer 2: cross-field rules
# ---------------------------------------------------------------------------


def rule_errors(record: dict[str, Any], *, strict: bool, base_dir: Path) -> list[str]:
    """Return ``"Rnn: message"`` strings. Assumes the schema layer passed or
    nearly passed; every access is defensive so a partially-formed record still
    gets useful rule messages."""
    errs: list[str] = []
    g = record.get

    family, group, tier, shape, status = g("family"), g("group"), g("tier"), g("shape"), g("status")
    scoring = g("scoring") or {}
    method = scoring.get("method")
    holdout = g("holdout") or {}
    prov = g("provenance") or {}
    todos = g("todos") or []

    # R01 family <-> group consistency
    if family in _FAMILY_GROUPS and group not in _FAMILY_GROUPS[family]:
        errs.append(f"R01: group {group!r} does not belong to family {family!r}")

    # R02 tier <-> scoring.method consistency
    if tier in _TIER_METHODS and method not in _TIER_METHODS[tier]:
        errs.append(
            f"R02: tier {tier} requires scoring.method in {sorted(_TIER_METHODS[tier])}, got {method!r}"
        )

    # R03 T1 needs an oracle with an independent measurement and a tolerance
    if tier == "T1_physics":
        oracle = scoring.get("oracle") or {}
        if not oracle:
            errs.append("R03: T1_physics requires scoring.oracle")
        elif "tolerance" not in oracle:
            errs.append("R03: T1_physics oracle must state a tolerance (abs/rel + units)")

    # R04 T2 needs a checker and shape B
    if tier == "T2_execution":
        if not scoring.get("checker"):
            errs.append("R04: T2_execution requires scoring.checker")
        if shape != "B_tool":
            errs.append("R04: T2_execution items must be shape B_tool (something has to execute)")

    # R05 T3 needs a non-null cutoff_date and a corpus snapshot
    if tier == "T3_reference":
        if not g("cutoff_date"):
            errs.append("R05: T3_reference requires a non-null cutoff_date")
        if not g("corpus_snapshot"):
            errs.append("R05: T3_reference requires corpus_snapshot (corpus_id + snapshot_ref)")

    # R06 T4 needs a judge block with >=2 raters; judge score never reportable without agreement
    if tier == "T4_judgment":
        judge = scoring.get("judge") or {}
        if not judge:
            errs.append("R06: T4_judgment requires scoring.judge")
        elif int(judge.get("min_raters", 0)) < 2:
            errs.append("R06: T4_judgment requires min_raters >= 2")

    # R07 shape B completeness / shape A exclusions
    if shape == "B_tool":
        for key in _SHAPE_B_REQUIRED:
            if key not in record:
                errs.append(f"R07: shape B_tool requires top-level {key!r}")
        if "record_submit" not in ((g("tools") or {}).get("allowlist") or []) and (
            (g("task") or {}).get("deliverable") in ("artifact", "script_and_artifact")
        ):
            errs.append("R07: artifact deliverables need record_submit in tools.allowlist")
    elif shape == "A_text":
        for key in _SHAPE_A_FORBIDDEN:
            if key in record:
                errs.append(f"R07: shape A_text must not carry {key!r}")
        if "reference_output" not in record and "reference_citations" not in record:
            errs.append("R07: shape A_text requires reference_output or reference_citations")

    # R08 holdout: test split must be private; paraphrase_only never on test
    if holdout.get("split") == "test" and holdout.get("visibility") != "private":
        errs.append("R08: split=test requires visibility=private")
    if holdout.get("split") == "test" and holdout.get("construction") == "paraphrase_only":
        errs.append(
            "R08: construction=paraphrase_only is not holdout-safe; not allowed on split=test"
        )

    # R09 catalog-derived items must say how they survive the corpus leak
    if prov.get("source_kind") in ("arcada_catalog", "arcada_paper_index"):
        if holdout.get("construction") in (None, "none"):
            errs.append(
                "R09: items derived from the aRCADA catalog or paper index must declare a holdout construction other than 'none'"
            )
        if not holdout.get("leakage_note"):
            errs.append("R09: catalog/paper-index derived items require holdout.leakage_note")

    # R10 status gates
    if status == "template":
        if not todos:
            errs.append("R10: status=template requires at least one entry in todos")
        if strict:
            errs.append("R10: --strict: template records are not allowed in a release build")
    if status in ("verified", "frozen"):
        if todos:
            errs.append(f"R10: status={status} must have zero todos (has {len(todos)})")
        if not prov.get("verification"):
            errs.append(f"R10: status={status} requires provenance.verification")
        if prov.get("author") in (None, "", "assistant-template"):
            errs.append(f"R10: status={status} requires a named human author")
    if status == "frozen" and shape == "B_tool":
        digest = (g("sandbox") or {}).get("image_digest", "TODO")
        if digest == "TODO" or not digest:
            errs.append("R10: status=frozen shape B requires sandbox.image_digest")

    # R11 no fabricated identifiers
    blob = json.dumps(record, default=str)
    for pref in _FAKE_DOI_PREFIXES:
        if pref in blob:
            errs.append(
                f"R11: placeholder DOI prefix {pref!r} found; use a real DOI or leave a TODO"
            )

    # R12 prompt must not leak the answer or checker internals
    prompt = (g("prompt") or "").lower()
    ref = record.get("reference_output")
    if isinstance(ref, str) and len(ref) > 40 and ref.lower() in prompt:
        errs.append("R12: reference_output text appears verbatim inside prompt")
    # Artifact keys are allowed in the prompt; the checker logic is not.
    if "checker" in prompt and "scoring" in prompt:
        errs.append("R12: prompt appears to describe the scoring checker")

    # R13 input files: hash check when the file is present locally
    for f in (g("inputs") or {}).get("files") or []:
        path = f.get("path", "")
        sha = f.get("sha256", "")
        candidates = [base_dir / path, PUBLIC_DATA_DIR / path, EXTERNAL_DATA_DIR / path]
        private_root = os.environ.get("FM_RCA_PRIVATE_DIR")
        if private_root:
            candidates.append(Path(private_root) / path)
        found = next((c for c in candidates if c.is_file()), None)
        if found is None:
            if holdout.get("visibility") == "public" and not path.startswith(
                ("mhz/", "chronfix/", "arcada/")
            ):
                errs.append(f"R13: public input file not found locally: {path}")
            # external/ groups are fetched by scripts/rca_fetch_external.py; absence is not an error
            continue
        if sha == "TODO":
            errs.append(f"R13: {path} is present; fill in its sha256 ({_sha256(found)[:12]}...)")
        elif _sha256(found) != sha:
            errs.append(f"R13: sha256 mismatch for {path}")

    # R14 photos need licence + attribution before any status past draft
    if status not in ("template", "draft"):
        for p in g("photos") or []:
            if p.get("permission_status") in ("unknown", "requested", "denied"):
                errs.append(
                    "R14: photo permission_status must be granted or not_needed before status advances"
                )

    # R15 sandbox network policy must be replay or none for frozen items
    if status == "frozen" and shape == "B_tool":
        net = (g("sandbox") or {}).get("network")
        if net == "allowlist":
            errs.append(
                "R15: frozen items must run network=replay or none; allowlist is for record mode only"
            )

    return errs


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Suite-level rules
# ---------------------------------------------------------------------------


def suite_errors(records: dict[Path, dict[str, Any]]) -> list[str]:
    errs: list[str] = []
    seen: dict[str, Path] = {}
    for path, rec in records.items():
        rid = rec.get("id")
        if rid in seen:
            errs.append(f"{path}: S01: duplicate id {rid!r} (also in {seen[rid]})")
        elif rid:
            seen[rid] = path
    return errs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def validate_paths(paths: Iterable[Path], *, strict: bool = False) -> tuple[int, list[str]]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    problems: list[str] = []
    records: dict[Path, dict[str, Any]] = {}
    n = 0
    for path in paths:
        n += 1
        try:
            rec = load_record(path)
        except Exception as exc:  # noqa: BLE001 - report and continue
            problems.append(f"{path}: load: {exc}")
            continue
        records[path] = rec
        for e in schema_errors(rec, schema):
            problems.append(f"{path}: {e}")
        for e in rule_errors(rec, strict=strict, base_dir=path.parent):
            problems.append(f"{path}: {e}")
    problems.extend(suite_errors(records))
    return n, problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("paths", nargs="*", help="record files or directories (default: seeds/)")
    ap.add_argument(
        "--strict", action="store_true", help="fail on status=template records (release builds)"
    )
    args = ap.parse_args(argv)

    n, problems = validate_paths(_iter_paths(args.paths), strict=args.strict)
    for p in problems:
        print(p)
    ok = not problems
    print(f"{'OK' if ok else 'FAIL'}: {n} record(s), {len(problems)} problem(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
