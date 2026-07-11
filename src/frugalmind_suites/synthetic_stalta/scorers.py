"""Scorer for the Ridgecrest synthetic STA/LTA suite.

The task gives a model a waveform + STA/LTA parameters and asks for the trigger
onset times as a JSON array. Scoring is `pick_f1` (reused from the
pipeline_regression Family-2 scorer): matched onsets within a tolerance, with
empty-vs-empty == 1.0 so a correct "no detection" on a negative case scores
perfectly. Deterministic, no LLM.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any


def metric_pick_f1(got: list[float], gold: list[float], *, tolerance: float) -> float:
    """F1 of predicted event times greedily matched to gold within ``tolerance``.

    Empty-vs-empty == 1.0 (a correct "no detection" on a negative case). Kept
    local so this suite is self-contained; the pipeline_regression Family-2
    scorer defines the same metric, and a shared module is a follow-up.
    """
    if not got and not gold:
        return 1.0
    if not got or not gold:
        return 0.0
    remaining = sorted(got)
    tp = 0
    for r in sorted(gold):
        best_i, best_d = None, tolerance
        for i, p in enumerate(remaining):
            d = abs(p - r)
            if d <= best_d:
                best_i, best_d = i, d
        if best_i is not None:
            remaining.pop(best_i)
            tp += 1
    precision = tp / len(got)
    recall = tp / len(gold)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _parse_pick_list(model_output: str) -> list[float]:
    """First parseable JSON array of numbers in the output (balanced scan)."""
    depth = 0
    start = None
    for i, ch in enumerate(model_output):
        if ch == "[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "]" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    arr = json.loads(model_output[start : i + 1])
                except json.JSONDecodeError:
                    start = None
                    continue
                if isinstance(arr, list):
                    nums = [x for x in arr if isinstance(x, (int, float))]
                    if len(nums) == len(arr):
                        return [float(x) for x in nums]
                start = None
    # Bare "none"/"no event" -> empty pick list (a valid negative answer).
    if re.search(r"\bno(ne)?\b|no event|not detected", model_output, re.I):
        return []
    return []


def make_detection_picks_scorer(
    *, tolerance_s: float = 1.5
) -> Callable[[str, Any], float]:
    """pick_f1 of reported onset times vs gold onsets within ``tolerance_s``."""

    def scorer(model_output: str, gold: Any) -> float:
        picks = _parse_pick_list(model_output)
        return metric_pick_f1(picks, gold or [], tolerance=tolerance_s)

    return scorer


def make_scorer_from_spec(spec: dict[str, Any]) -> Callable[[str, Any], float]:
    """Reconstruct a scorer from a JSON-serialisable spec.

    Recognised names: ``detection_picks``, ``zero``.
    """
    name = spec["name"]
    config = dict(spec.get("config", {}))
    if name == "detection_picks":
        return make_detection_picks_scorer(
            tolerance_s=config.get("tolerance_s", 1.5)
        )
    if name == "zero":
        return lambda _out, _gold: 0.0
    raise ValueError(f"unknown scorer name: {name!r}")
