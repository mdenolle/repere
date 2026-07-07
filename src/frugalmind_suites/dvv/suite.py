"""FrugalMind benchmark suites for dv/v processing, backed by codameter.

Thin adapter: all synthesis, pipeline execution and scoring live in
``codameter.frugalmind``; this wraps the rows in FrugalMind's
``DenolleGroupSuite`` / ``BenchmarkRow`` contract.

Two suites, one per output type:

- ``DVVParamRecommendationSuite`` (``param_recommendation``) -- the model returns
  a processing-choice config; the scorer runs it on the hidden synthetic and
  grades recovery of the known dv/v. Cheap, deterministic, sandbox-free.
- ``DVVSeriesSuite`` (``dvv_series``) -- the model returns the recovered dv/v(t)
  series (a ReAct agent runs codameter in the sandbox and prints the array); the
  scorer regresses it against the truth, anchored so a no-change series scores ~0.

``codameter`` is imported lazily, so this module imports even when codameter is
absent; building rows or scoring then raises a clear error. Install the suite's
extra to enable it: ``pip install frugalmind[dvv]``.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from typing import Any

from frugalmind import DenolleGroupSuite, TaskKind
from frugalmind.export import BenchmarkRow

DATASET_ID = "dvv_processing"
VERSION = "v0.1"
_VALID_SPLITS = ("validation", "test")


def _cfm():
    """Import codameter's FrugalMind adapter lazily, with an actionable error."""
    try:
        from codameter import frugalmind as cfm
    except ImportError as exc:  # pragma: no cover - exercised only without codameter
        raise ImportError(
            "the dv/v suite needs codameter; install it with "
            "`pip install frugalmind[dvv]` (or `pip install codameter`)."
        ) from exc
    return cfm


def _env_split(explicit: str | None) -> str | None:
    split = explicit if explicit is not None else os.environ.get("FM_DVV_SPLIT")
    if split in (None, "", "all"):
        return None
    if split not in _VALID_SPLITS:
        raise ValueError(f"split must be one of {_VALID_SPLITS} or None; got {split!r}")
    return split


class _DVVSuite(DenolleGroupSuite):
    task: str = ""
    task_kind = TaskKind.CODE_GENERATION
    dataset_id = DATASET_ID
    version = VERSION

    def __init__(self, split: str | None = None, visibility: str | None = None) -> None:
        self.split = _env_split(split)
        self.visibility = visibility

    def _rows(self) -> list[dict]:
        return _cfm().build_rows(self.task, split=self.split, visibility=self.visibility)

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        make = _cfm().make_scorer_from_spec
        for r in self._rows():
            yield (r["prompt"], r["gold"], make(r["scorer_spec"]))

    def export_rows(self) -> Iterable[BenchmarkRow]:
        for r in self._rows():
            yield BenchmarkRow(**r)


class DVVParamRecommendationSuite(_DVVSuite):
    task = "param_recommendation"
    suite_id = "param_recommendation"


class DVVSeriesSuite(_DVVSuite):
    task = "dvv_series"
    suite_id = "dvv_series"


ALL_SUITES = [DVVParamRecommendationSuite(), DVVSeriesSuite()]
