"""Pipeline-regression suite (Family 2: coding agents, data-out).

One suite over a shared truth set (`pipelines.yaml`). Each item asks the model
to drive a real scientific pipeline and report a numeric result via
``record(...)``; the `numerical_regression` scorer compares it to a reference
with a numeric tolerance and no LLM in the loop.

Mirrors the STA/LTA suite structure: a single `_compose()` feeds both
``items()`` (runtime scorers) and ``export_rows()`` (curated JSONL), so there
is zero drift between what runs and what ships.
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

_DEFAULT_PIPELINES = Path(__file__).parent / "pipelines.yaml"
PIPELINES_PATH = Path(os.environ.get("REPERE_PIPELINES", _DEFAULT_PIPELINES))

VALID_SPLITS = ("validation", "test")
VALID_VISIBILITIES = ("public", "private")


def _resolve_split(split: str | None) -> str | None:
    if split is None:
        env = os.environ.get("REPERE_PIPELINES_SPLIT")
        if env in (None, "", "all"):
            return None
        split = env
    if split not in VALID_SPLITS:
        raise ValueError(f"split must be one of {VALID_SPLITS} or None; got {split!r}")
    return split


def _load_pipelines(split: str | None = None) -> list[dict]:
    if not PIPELINES_PATH.exists():
        raise FileNotFoundError(f"{PIPELINES_PATH} not found")
    data = yaml.safe_load(PIPELINES_PATH.read_text())
    items = data["pipelines"]
    required_keys = (
        "id", "tool", "label", "artifact_key", "metric", "gold", "split", "visibility"
    )
    for p in items:
        for required in required_keys:
            if required not in p:
                raise ValueError(f"pipeline {p.get('id')!r} missing key {required!r}")
        if p["split"] not in VALID_SPLITS:
            raise ValueError(f"pipeline {p['id']!r}: bad split {p['split']!r}")
        if p["visibility"] not in VALID_VISIBILITIES:
            raise ValueError(f"pipeline {p['id']!r}: bad visibility {p['visibility']!r}")
    split = _resolve_split(split)
    if split is not None:
        items = [p for p in items if p["split"] == split]
    return items


# Metric-specific config keys carried through into the scorer spec.
_METRIC_KEYS = ("tolerance", "rtol", "atol", "rmse_scale")


class PipelineRegressionSuite(DenolleGroupSuite):
    """Prompt → pipeline run → numeric output, scored by regression."""

    task_kind = TaskKind.NUMERICAL_REGRESSION
    dataset_id = "pipeline_regression"
    suite_id = "pipeline_regression"
    version = "v0.1"

    def __init__(self, *, split: str | None = None) -> None:
        self.split = _resolve_split(split)

    def _pipelines(self) -> list[dict]:
        return _load_pipelines(split=self.split)

    def _compose(self, p: dict) -> tuple[str, Any, dict, dict]:
        prompt = (
            f"Task: {p['label'].strip()}\n\n"
            f"Use the `{p['tool']}` pipeline. Write a single Python snippet that "
            f"computes the result and reports it by calling "
            f"record({p['artifact_key']}=<value>). `record` is a harness helper "
            f"that captures values for scoring; the value must be JSON-serialisable "
            f"(a number or a list of numbers).\n"
            "Return only the code in a single ```python fenced block."
        )
        gold = p["gold"]

        config: dict[str, Any] = {
            "artifact_key": p["artifact_key"],
            "metric": p["metric"],
            "required_calls": [f"record({p['artifact_key']}"],
        }
        for k in _METRIC_KEYS:
            if k in p:
                config[k] = p[k]
        # Per-suite sandbox image (heavy pipeline deps) travels in the spec so
        # the docker backend resolves the right image at score time (P2.2 uses
        # one image; regression suites override per tool). Host backend ignores it.
        if p.get("sandbox_image"):
            config["sandbox_image"] = p["sandbox_image"]
        scorer_spec = {"name": "numerical_regression", "config": config}

        meta = {
            "pipeline_id": p["id"],
            "tool": p["tool"],
            "metric": p["metric"],
            "sandbox_image": p.get("sandbox_image"),
        }
        return prompt, gold, scorer_spec, meta

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for p in self._pipelines():
            prompt, gold, scorer_spec, _ = self._compose(p)
            yield (prompt, gold, make_scorer_from_spec(scorer_spec))

    def export_rows(self) -> Iterable[BenchmarkRow]:
        for p in self._pipelines():
            prompt, gold, scorer_spec, meta = self._compose(p)
            yield BenchmarkRow(
                id=f"{self.dataset_id}/{self.suite_id}/{p['id']}",
                dataset_id=self.dataset_id,
                suite_id=self.suite_id,
                version=self.version,
                task_kind=self.task_kind.value,
                split=p["split"],
                visibility=p["visibility"],
                prompt=prompt,
                gold=gold,
                scorer_spec=scorer_spec,
                metadata=meta,
            )


ALL_SUITES = (PipelineRegressionSuite,)
