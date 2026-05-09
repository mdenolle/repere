"""JSONL telemetry sink for FrugalMind eval and routing runs.

Telemetry records are append-only JSON Lines so a long run can be tailed and
parsed by external tooling without re-reading the whole file. Each record is
flushed individually so a crash leaves a recoverable file.
"""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import AbstractContextManager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


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

    Usage:

        with JSONLTelemetry("results/run.jsonl", run_metadata={"suite": "stalta"}) as tel:
            tel.log_event("generation", {"model_id": "m1", "score": 0.7})
            tel.log_generation(generation, score=0.5)
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        run_metadata: Mapping[str, Any] | None = None,
        write_run_header: bool = True,
        clock: Any = time.time,
    ) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._handle: Any = None
        self._run_metadata: dict[str, Any] = dict(run_metadata or {})
        self._write_run_header = write_run_header
        self._closed = False
        self._clock = clock

    @property
    def path(self) -> Path:
        return self._path

    def __enter__(self) -> "JSONLTelemetry":
        self._handle = open(self._path, "a", encoding="utf-8")
        if self._write_run_header:
            self._write(
                {
                    "type": "run_start",
                    "ts": _utc_now_iso(),
                    "metadata": self._run_metadata,
                }
            )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._handle is not None:
            try:
                self._write(
                    {
                        "type": "run_end",
                        "ts": _utc_now_iso(),
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
        record: dict[str, Any] = {"type": event_type, "ts": _utc_now_iso()}
        if payload is not None:
            record["payload"] = _coerce(payload)
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
        gen = _coerce(generation)
        record: dict[str, Any] = {
            "type": "generation",
            "ts": _utc_now_iso(),
            "generation": gen,
        }
        if score is not None:
            record["score"] = float(score)
        if suite is not None:
            record["suite"] = suite
        if item_index is not None:
            record["item_index"] = int(item_index)
        if skill_name is not None:
            record["skill_name"] = skill_name
        if skill_mode is not None:
            record["skill_mode"] = skill_mode
        if extra:
            record["extra"] = dict(extra)
        self._write(record)

    def close(self) -> None:
        self.__exit__(None, None, None)


def read_jsonl(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Helper: read a JSONL telemetry file into memory (for tests and tools)."""
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


__all__ = ["JSONLTelemetry", "read_jsonl"]
