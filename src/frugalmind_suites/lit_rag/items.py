"""Literature / RAG / translation suites (Family 1), verifiable-core.

Three thin suites over one truth set (`tasks.yaml`), one per deterministic
scorer, mirroring the STA/LTA one-suite-per-kind structure. Each task in the
YAML carries its own serialisable ``scorer`` spec, so ``_compose`` is trivial
and ``items()``/``export_rows()`` share a single source of truth.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import yaml

from frugalmind import DenolleGroupSuite, TaskKind
from frugalmind.export import BenchmarkRow

from .scorers import make_scorer_from_spec

_DEFAULT_TASKS = Path(__file__).parent / "tasks.yaml"
TASKS_PATH = Path(os.environ.get("FM_LITRAG_TASKS", _DEFAULT_TASKS))

VALID_SPLITS = ("validation", "test")
VALID_VISIBILITIES = ("public", "private")


def _resolve_split(split: str | None) -> str | None:
    if split is None:
        env = os.environ.get("FM_LITRAG_SPLIT")
        if env in (None, "", "all"):
            return None
        split = env
    if split not in VALID_SPLITS:
        raise ValueError(f"split must be one of {VALID_SPLITS} or None; got {split!r}")
    return split


def _load_tasks(kind: str, split: str | None = None) -> list[dict]:
    if not TASKS_PATH.exists():
        raise FileNotFoundError(f"{TASKS_PATH} not found")
    data = yaml.safe_load(TASKS_PATH.read_text())
    tasks = data["tasks"]
    for t in tasks:
        for required in ("id", "kind", "prompt", "gold", "scorer", "split", "visibility"):
            if required not in t:
                raise ValueError(f"task {t.get('id')!r} missing key {required!r}")
    tasks = [t for t in tasks if t["kind"] == kind]
    split = _resolve_split(split)
    if split is not None:
        tasks = [t for t in tasks if t["split"] == split]
    return tasks


class _LitRagSuite(DenolleGroupSuite):
    """Base: filter one truth set by ``_kind`` and split; scorer from the row."""

    _kind: str
    dataset_id = "lit_rag"

    def __init__(self, *, split: str | None = None) -> None:
        self.split = _resolve_split(split)

    def _tasks(self) -> list[dict]:
        return _load_tasks(self._kind, split=self.split)

    def _compose(self, t: dict) -> tuple[str, Any, dict, dict]:
        prompt = t["prompt"].strip()
        gold = t["gold"]
        scorer_spec = t["scorer"]
        meta = {"task_id": t["id"], "kind": t["kind"]}
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


class LitRagRetrievalSuite(_LitRagSuite):
    """RAG retrieval: rank documents against a gold relevant set."""

    _kind = "retrieval"
    task_kind = TaskKind.RETRIEVAL
    suite_id = "retrieval"
    version = "v0.1"


class LitRagTranslationSuite(_LitRagSuite):
    """Translation with domain-term preservation."""

    _kind = "translation"
    task_kind = TaskKind.TRANSLATION
    suite_id = "translation"
    version = "v0.1"


class LitRagGroundedQASuite(_LitRagSuite):
    """Grounded QA: citation-supported answers, no fabricated sources."""

    _kind = "grounded_qa"
    task_kind = TaskKind.GROUNDED_QA
    suite_id = "grounded_qa"
    version = "v0.1"


ALL_SUITES = (
    LitRagRetrievalSuite,
    LitRagTranslationSuite,
    LitRagGroundedQASuite,
)
