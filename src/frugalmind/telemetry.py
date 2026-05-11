"""JSONL telemetry sink for FrugalMind eval and routing runs.

Telemetry records are append-only JSON Lines so a long run can be tailed and
parsed by external tooling without re-reading the whole file. Each record is
flushed individually so a crash leaves a recoverable file.

Schema
------

This module writes **schema version 2** (P2.5), which aligns field names with
InspectAI's ``EvalSample`` / ``EvalOutput`` so the data shape maps cleanly to
Inspect's ``.eval`` log format. Specifically:

- ``run_start`` records carry ``schema_version``, ``run_id`` (UUID4),
  ``task``, ``task_args``, ``solver``, ``model``, and ``created``.
- Per-sample records use ``type="sample"`` (not ``"generation"``) and carry
  ``id``, ``epoch``, ``output`` (the generation), and ``run_id`` to link back
  to the ``run_start``.
- ``run_end`` records also carry ``run_id`` and ``completed``.

For backwards compatibility, :func:`read_jsonl` accepts v1 logs (no
``schema_version`` field, ``type="generation"`` with the inner key
``generation``) and normalises them in memory to the v2 shape. v1 records
gain a ``schema_version: 1`` marker so callers know they were migrated.

The full field-mapping table lives in ``docs/telemetry.md``.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Bumped from 1 → 2 in P2.5. v1 → v2 read-time normalisation lives in
# :func:`read_jsonl`; on-disk migration is intentionally out of scope.
TELEMETRY_SCHEMA_VERSION = 2


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce(record: Any) -> dict[str, Any]:
    if isinstance(record, Mapping):
        return dict(record)
    if is_dataclass(record):
        return asdict(record)
    raise TypeError(f"telemetry record must be a Mapping or dataclass, got {type(record)!r}")


class JSONLTelemetry(AbstractContextManager):
    """Thread-safe JSONL sink with optional run metadata.

    Writes schema version 2 records (P2.5). New constructor kwargs ``task``,
    ``task_args``, ``solver``, and ``model`` are surfaced on the ``run_start``
    record so downstream tooling (Inspect's log viewer, our own dashboard)
    can attribute each sample to its run. All four are optional — passing
    ``None`` (the default) just omits the field.

    Usage::

        with JSONLTelemetry(
            "results/run.jsonl",
            task="sta_lta.intent_extraction",
            solver="generate",
            model="claude-haiku-4-5",
        ) as tel:
            tel.log_event("budget_skip", {"model_id": "m1", "estimate_usd": 0.02})
            tel.log_sample(generation, score=0.7, suite="sta_lta.intent_extraction", epoch=0)

    The legacy ``log_generation`` name is kept as a thin alias for callers
    that haven't migrated yet — it writes the same v2 record shape.
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        run_metadata: Mapping[str, Any] | None = None,
        write_run_header: bool = True,
        clock: Any = time.time,
        # New in v2 — surface Inspect-style run-level attribution.
        run_id: str | None = None,
        task: str | None = None,
        task_args: Mapping[str, Any] | None = None,
        solver: str | None = None,
        model: str | None = None,
    ) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._handle: Any = None
        self._run_metadata: dict[str, Any] = dict(run_metadata or {})
        self._write_run_header = write_run_header
        self._closed = False
        self._clock = clock
        # Deterministic-by-default but caller-overridable run id. UUID4 keeps
        # collision probability negligible across machines; tests pass an
        # explicit value when they want assertion stability.
        self._run_id: str = run_id or uuid.uuid4().hex
        self._task = task
        self._task_args: dict[str, Any] = dict(task_args or {})
        self._solver = solver
        self._model = model

    @property
    def path(self) -> Path:
        return self._path

    @property
    def run_id(self) -> str:
        """Stable id stamped on every record in this run."""
        return self._run_id

    def __enter__(self) -> JSONLTelemetry:
        self._handle = open(self._path, "a", encoding="utf-8")
        if self._write_run_header:
            header: dict[str, Any] = {
                "type": "run_start",
                "schema_version": TELEMETRY_SCHEMA_VERSION,
                "ts": _utc_now_iso(),
                "run_id": self._run_id,
                "created": _utc_now_iso(),
                "metadata": self._run_metadata,
            }
            # Only emit run-level fields when the caller actually provided
            # them — keeps records small and avoids advertising null
            # attribution we don't have.
            if self._task is not None:
                header["task"] = self._task
            if self._task_args:
                header["task_args"] = self._task_args
            if self._solver is not None:
                header["solver"] = self._solver
            if self._model is not None:
                header["model"] = self._model
            self._write(header)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._handle is not None:
            try:
                self._write(
                    {
                        "type": "run_end",
                        "schema_version": TELEMETRY_SCHEMA_VERSION,
                        "ts": _utc_now_iso(),
                        "run_id": self._run_id,
                        "completed": _utc_now_iso(),
                        "ok": exc_type is None,
                    }
                )
            finally:
                self._handle.close()
                self._handle = None
        self._closed = True

    def _write(self, record: dict[str, Any]) -> None:
        if self._closed:
            raise RuntimeError("JSONLTelemetry is closed")
        if self._handle is None:
            # Lazily open if used outside a `with` block (e.g., for tests).
            self._handle = open(self._path, "a", encoding="utf-8")
        line = json.dumps(record, default=str) + "\n"
        with self._lock:
            self._handle.write(line)
            self._handle.flush()

    def log_event(self, event_type: str, payload: Any | None = None) -> None:
        record: dict[str, Any] = {
            "type": event_type,
            "schema_version": TELEMETRY_SCHEMA_VERSION,
            "ts": _utc_now_iso(),
            "run_id": self._run_id,
        }
        if payload is not None:
            record["payload"] = _coerce(payload)
        self._write(record)

    def log_sample(
        self,
        generation: Any,
        *,
        score: float | None = None,
        suite: str | None = None,
        epoch: int | None = None,
        sample_id: str | None = None,
        skill_name: str | None = None,
        skill_mode: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        """Log a single sample record (v2 schema).

        Mirrors Inspect's ``EvalSample`` shape:

        - ``id``: stable per-sample identifier. Defaults to
          ``f"{suite}:{epoch}"`` when ``sample_id`` is not passed and both
          ``suite`` and ``epoch`` are known.
        - ``epoch``: the position of this sample within its suite (formerly
          ``item_index``). Kept as an int so it sorts naturally.
        - ``output``: the dict / dataclass that holds the model's generation
          (formerly ``generation``). Inspect's ``EvalOutput`` shape lives
          inside here unchanged.

        FrugalMind-specific fields without an Inspect analog (``suite``,
        ``score``, ``skill_name``, ``skill_mode``) stay as-is.
        """
        gen = _coerce(generation)

        # Synthesise sample_id from (suite, epoch) when caller doesn't pass
        # one — gives a stable, human-readable key. Falls back to the run_id
        # when neither is known so every record still has an id.
        derived_id: str | None
        if sample_id is not None:
            derived_id = sample_id
        elif suite is not None and epoch is not None:
            derived_id = f"{suite}:{epoch}"
        elif epoch is not None:
            derived_id = f"sample:{epoch}"
        else:
            derived_id = None

        record: dict[str, Any] = {
            "type": "sample",
            "schema_version": TELEMETRY_SCHEMA_VERSION,
            "ts": _utc_now_iso(),
            "run_id": self._run_id,
            "output": gen,
        }
        if derived_id is not None:
            record["id"] = derived_id
        if score is not None:
            record["score"] = float(score)
        if suite is not None:
            record["suite"] = suite
        if epoch is not None:
            record["epoch"] = int(epoch)
        if skill_name is not None:
            record["skill_name"] = skill_name
        if skill_mode is not None:
            record["skill_mode"] = skill_mode
        if extra:
            record["extra"] = dict(extra)
        self._write(record)

    def log_generation(
        self,
        generation: Any,
        *,
        score: float | None = None,
        suite: str | None = None,
        item_index: int | None = None,
        skill_name: str | None = None,
        skill_mode: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        """Legacy alias for :meth:`log_sample`.

        Translates the old ``item_index`` keyword to v2's ``epoch`` and forwards
        to ``log_sample``. Kept so external callers (notebooks, downstream
        tooling) don't break on the v1 → v2 cutover. Schedule removal once
        every in-tree caller has migrated.
        """
        self.log_sample(
            generation,
            score=score,
            suite=suite,
            epoch=item_index,
            skill_name=skill_name,
            skill_mode=skill_mode,
            extra=extra,
        )

    def close(self) -> None:
        self.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Read path — v1 → v2 compatibility shim
# ---------------------------------------------------------------------------


def _normalise_v1_to_v2(record: dict[str, Any]) -> dict[str, Any]:
    """Translate a v1 telemetry record to the v2 shape **in memory**.

    v1 records have no ``schema_version`` field. The differences:

    - per-sample records use ``type="generation"`` with the dict on key
      ``generation``; v2 uses ``type="sample"`` with the dict on key
      ``output``.
    - per-sample records use ``item_index``; v2 uses ``epoch``.
    - per-sample records have no synthesised ``id``; v2 sets
      ``f"{suite}:{epoch}"`` when both are known.
    - ``run_start`` / ``run_end`` / event records have no ``run_id``; we
      leave them with the original ``type``-and-``metadata`` shape but tag
      ``schema_version: 1`` so callers know not to expect a ``run_id``.
    """
    out = dict(record)
    out.setdefault("schema_version", 1)

    rtype = out.get("type")
    if rtype == "generation":
        out["type"] = "sample"
        if "generation" in out and "output" not in out:
            out["output"] = out.pop("generation")
        if "item_index" in out:
            # Always rewrite item_index → epoch so the v2 shape is clean.
            # Without ``pop`` callers would see *both* fields on migrated
            # records, which would silently mask drift between schemas.
            if "epoch" not in out:
                out["epoch"] = int(out["item_index"])
            out.pop("item_index", None)
        # Synthesise id only when both bits are present; otherwise leave the
        # record id-less so callers can detect partial v1 logs.
        if "id" not in out and "suite" in out and "epoch" in out:
            out["id"] = f"{out['suite']}:{out['epoch']}"
        elif "id" not in out and "epoch" in out:
            out["id"] = f"sample:{out['epoch']}"
    return out


def read_jsonl(
    path: str | os.PathLike[str],
    *,
    normalise: bool = True,
) -> list[dict[str, Any]]:
    """Read a JSONL telemetry file into memory.

    By default, v1 records are silently normalised to the v2 shape so
    downstream code only ever handles one schema. Pass ``normalise=False``
    to get the raw on-disk records (useful for tests asserting on-disk
    bytes, or for tooling that needs to detect schema drift).
    """
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if normalise and "schema_version" not in record:
                record = _normalise_v1_to_v2(record)
            out.append(record)
    return out


__all__ = ["JSONLTelemetry", "TELEMETRY_SCHEMA_VERSION", "read_jsonl"]
