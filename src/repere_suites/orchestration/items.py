"""Orchestration suite (Family 3): non-linear subagent workflows.

One suite over `tasks.yaml`. Each task's correct solution is a DAG of subagent
calls; the `trajectory_dag` scorer grades the emitted plan. Each YAML row
carries its own serialisable ``scorer`` spec, so ``_compose`` is trivial and
``items()``/``export_rows()`` share one source of truth.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import yaml

from repere import DenolleGroupSuite, TaskKind
from repere.export import BenchmarkRow

from .scorers import make_scorer_from_spec

_DEFAULT_TASKS = Path(__file__).parent / "tasks.yaml"
TASKS_PATH = Path(os.environ.get("REPERE_ORCH_TASKS", _DEFAULT_TASKS))

VALID_SPLITS = ("validation", "test")
VALID_VISIBILITIES = ("public", "private")


def _resolve_split(split: str | None) -> str | None:
    if split is None:
        env = os.environ.get("REPERE_ORCH_SPLIT")
        if env in (None, "", "all"):
            return None
        split = env
    if split not in VALID_SPLITS:
        raise ValueError(f"split must be one of {VALID_SPLITS} or None; got {split!r}")
    return split


def _load_tasks(split: str | None = None) -> list[dict]:
    if not TASKS_PATH.exists():
        raise FileNotFoundError(f"{TASKS_PATH} not found")
    data = yaml.safe_load(TASKS_PATH.read_text())
    tasks = data["tasks"]
    for t in tasks:
        for required in ("id", "prompt", "gold", "scorer", "split", "visibility"):
            if required not in t:
                raise ValueError(f"task {t.get('id')!r} missing key {required!r}")
    split = _resolve_split(split)
    if split is not None:
        tasks = [t for t in tasks if t["split"] == split]
    return tasks


class OrchestrationSuite(DenolleGroupSuite):
    """Goal → DAG of subagent calls, scored on node/edge F1 + frugality."""

    task_kind = TaskKind.ORCHESTRATION
    dataset_id = "orchestration"
    suite_id = "orchestration"
    version = "v0.1"

    def __init__(self, *, split: str | None = None) -> None:
        self.split = _resolve_split(split)

    def _tasks(self) -> list[dict]:
        return _load_tasks(split=self.split)

    def _compose(self, t: dict) -> tuple[str, Any, dict, dict]:
        prompt = t["prompt"].strip()
        gold = t["gold"]
        scorer_spec = t["scorer"]
        meta = {
            "task_id": t["id"],
            "available_agents": t.get("available_agents", []),
            "max_calls": t["scorer"].get("config", {}).get("max_calls"),
        }
        return prompt, gold, scorer_spec, meta

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for t in self._tasks():
            prompt, gold, scorer_spec, _ = self._compose(t)
            yield (prompt, gold, make_scorer_from_spec(scorer_spec))

    def export_rows(self) -> Iterable[BenchmarkRow]:
        for t in self._tasks():
            prompt, gold, scorer_spec, meta = self._compose(t)
            yield BenchmarkRow(
                id=f"{self.dataset_id}/{self.suite_id}/{t['id']}",
                dataset_id=self.dataset_id,
                suite_id=self.suite_id,
                version=self.version,
                task_kind=self.task_kind.value,
                split=t["split"],
                visibility=t["visibility"],
                prompt=prompt,
                gold=gold,
                scorer_spec=scorer_spec,
                metadata=meta,
            )


ALL_SUITES = (OrchestrationSuite,)
