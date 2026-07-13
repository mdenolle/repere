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


# ---------------------------------------------------------------------------
# stalta_code — the coding-agent form of the task
#
# Asking a model to *mentally execute* a DSP algorithm over ~1000 raw samples
# pasted into the prompt is not a meaningful eval: no LLM can do it, every model
# scores 0, and the column cannot discriminate. (A live 7B run confirmed this —
# it replies "what would you like me to do with these numbers?")
#
# The realistic agent task is to WRITE THE DETECTOR. The waveform is injected
# into the sandbox as a pre-defined `waveform` / `fs`, the model's code runs
# there, and we grade the onsets it reports via `record(picks=[...])` with the
# same pick_f1 metric. This is the Family-2 prompt -> code -> execute pattern.
# ---------------------------------------------------------------------------

_DEFAULT_STAGE_WEIGHTS = {"code": 0.1, "runs": 0.1, "accuracy": 0.8}


def make_stalta_code_scorer(
    *,
    waveform: list[float],
    fs: float,
    tolerance_s: float = 1.5,
    timeout_s: float = 60.0,
    stage_weights: dict[str, float] | None = None,
) -> Callable[[str, Any], float]:
    """Run the model's STA/LTA code in the sandbox and grade the picks it records.

    Staged, accuracy-weighted: a snippet that merely runs but reports the wrong
    onsets caps at 0.2, well below one that actually finds the event.
    """
    from frugalmind_suites.sta_lta.sandbox import extract_code, run_snippet

    weights = {**_DEFAULT_STAGE_WEIGHTS, **(stage_weights or {})}
    # The data the model's code operates on. Injected rather than pasted into
    # the prompt so the model writes a detector instead of transcribing numbers.
    setup = f"waveform = {json.dumps(list(waveform))}\nfs = {float(fs)!r}\n"

    def scorer(model_output: str, gold: Any) -> float:
        code = extract_code(model_output)
        if not code:
            return 0.0
        score = weights["code"]
        result = run_snippet(setup + "\n" + code, timeout_s=timeout_s)
        if result.ok and "picks" in result.artifacts:
            score += weights["runs"]
            picks = result.artifacts["picks"]
            if not isinstance(picks, list):
                picks = []
            try:
                picks = [float(p) for p in picks]
            except (TypeError, ValueError):
                picks = []
            acc = metric_pick_f1(picks, list(gold or []), tolerance=tolerance_s)
            score += weights["accuracy"] * acc
        return max(0.0, min(1.0, score))

    return scorer


def make_scorer_from_spec(spec: dict[str, Any]) -> Callable[[str, Any], float]:
    """Reconstruct a scorer from a JSON-serialisable spec.

    Recognised names: ``stalta_code``, ``detection_picks``, ``zero``.
    """
    name = spec["name"]
    config = dict(spec.get("config", {}))
    if name == "stalta_code":
        return make_stalta_code_scorer(
            waveform=config["waveform"],
            fs=config["fs"],
            tolerance_s=config.get("tolerance_s", 1.5),
            timeout_s=config.get("timeout_s", 60.0),
            stage_weights=config.get("stage_weights"),
        )
    if name == "detection_picks":
        return make_detection_picks_scorer(
            tolerance_s=config.get("tolerance_s", 1.5)
        )
    if name == "zero":
        return lambda _out, _gold: 0.0
    raise ValueError(f"unknown scorer name: {name!r}")
