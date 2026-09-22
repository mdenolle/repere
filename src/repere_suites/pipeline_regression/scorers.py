"""Numerical-regression scorer (tier T1) for pipeline-output tasks.

Family 2 "coding agents, data-out": the model drives a real scientific
pipeline (seisbench phase picking, noisepy cross-correlation, codameter coda
measurements) and reports a *numeric* result through the sandbox's
``record(**kwargs)`` helper. Correctness is "is the number right, within
tolerance?" — compared to a reference with **no LLM in the loop**.

The scorer reuses the STA/LTA sandbox (`run_snippet`, `extract_code`) so the
execution + artefact-capture contract is identical across suites. See
``docs/numerical_regression_scorer.md`` for the design.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from repere_suites.sta_lta.sandbox import extract_code, run_snippet

# ---------------------------------------------------------------------------
# Metrics — pure Python, no numpy dependency in the scorer path (mirrors the
# optional-scikit-image caution in the plot_ssim scorer). Each returns a
# graded accuracy in [0, 1]; higher is closer to the reference.
# ---------------------------------------------------------------------------


def _flatten(x: Any) -> list[float] | None:
    """Flatten a scalar / (nested) list into a flat list of floats.

    Returns None if any leaf is not coercible to float — the caller treats
    that as accuracy 0.0 rather than raising, so one malformed model output
    never sinks a run.
    """
    out: list[float] = []

    def _walk(v: Any) -> bool:
        # Depth-first, preserving left-to-right order.
        if isinstance(v, (list, tuple)):
            for item in v:
                if not _walk(item):
                    return False
            return True
        try:
            out.append(float(v))
            return True
        except (TypeError, ValueError):
            return False

    return out if _walk(x) else None


def metric_pick_f1(got: Any, gold: Any, *, tolerance: float) -> float:
    """F1 of predicted event times matched to reference within ``tolerance`` s.

    Greedy nearest-match, each reference time consumes at most one prediction.
    Empty-vs-empty scores 1.0 — the regression analogue of a correct negative
    case (a pipeline that correctly returns no picks).
    """
    g = _flatten(got)
    ref = _flatten(gold)
    if g is None or ref is None:
        return 0.0
    if not g and not ref:
        return 1.0
    if not g or not ref:
        return 0.0

    remaining = sorted(g)
    tp = 0
    for r in sorted(ref):
        best_i, best_d = None, tolerance
        for i, p in enumerate(remaining):
            d = abs(p - r)
            if d <= best_d:
                best_i, best_d = i, d
        if best_i is not None:
            remaining.pop(best_i)
            tp += 1

    precision = tp / len(g)
    recall = tp / len(ref)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def metric_allclose(got: Any, gold: Any, *, rtol: float, atol: float) -> float:
    """Fraction of entries within ``atol + rtol*|gold|`` (elementwise)."""
    g = _flatten(got)
    ref = _flatten(gold)
    if g is None or ref is None or len(g) != len(ref) or not ref:
        return 0.0
    hits = sum(
        1 for a, b in zip(g, ref, strict=False) if abs(a - b) <= atol + rtol * abs(b)
    )
    return hits / len(ref)


def metric_pearson(got: Any, gold: Any) -> float:
    """max(0, Pearson r) of flattened vectors — a shape metric for CCFs."""
    g = _flatten(got)
    ref = _flatten(gold)
    if g is None or ref is None or len(g) != len(ref) or len(ref) < 2:
        return 0.0
    n = len(ref)
    mg = sum(g) / n
    mr = sum(ref) / n
    cov = sum((a - mg) * (b - mr) for a, b in zip(g, ref, strict=False))
    vg = math.sqrt(sum((a - mg) ** 2 for a in g))
    vr = math.sqrt(sum((b - mr) ** 2 for b in ref))
    if vg == 0 or vr == 0:
        return 0.0
    return max(0.0, cov / (vg * vr))


def metric_rmse(got: Any, gold: Any, *, rmse_scale: float) -> float:
    """max(0, 1 - rmse/rmse_scale). Requires a positive ``rmse_scale``."""
    g = _flatten(got)
    ref = _flatten(gold)
    if g is None or ref is None or len(g) != len(ref) or not ref or rmse_scale <= 0:
        return 0.0
    rmse = math.sqrt(sum((a - b) ** 2 for a, b in zip(g, ref, strict=False)) / len(ref))
    return max(0.0, 1.0 - rmse / rmse_scale)


_DEFAULT_STAGE_WEIGHTS = {"code": 0.1, "calls": 0.1, "runs": 0.1, "accuracy": 0.7}


def _accuracy(metric: str, got: Any, gold: Any, config: dict[str, Any]) -> float:
    if metric == "pick_f1":
        return metric_pick_f1(got, gold, tolerance=config.get("tolerance", 0.5))
    if metric == "allclose":
        return metric_allclose(
            got, gold, rtol=config.get("rtol", 1e-3), atol=config.get("atol", 1e-6)
        )
    if metric == "pearson":
        return metric_pearson(got, gold)
    if metric == "rmse":
        return metric_rmse(got, gold, rmse_scale=config.get("rmse_scale", 1.0))
    raise ValueError(f"unknown numerical_regression metric: {metric!r}")


def make_numerical_regression_scorer(
    *,
    artifact_key: str,
    metric: str = "allclose",
    required_calls: list[str] | None = None,
    stage_weights: dict[str, float] | None = None,
    timeout_s: float = 60.0,
    sandbox_image: str | None = None,
    **metric_config: Any,
) -> Callable[[str, Any], float]:
    """Score a pipeline's numeric output against a reference.

    Staged like ``code_execution`` but the final stage is **graded**, not
    binary: a pipeline that runs yet returns wrong numbers scores at most the
    non-accuracy weight (0.30 by default), well below a correct run.

    * ``artifact_key`` — the ``record(...)`` key holding the numeric output.
    * ``metric`` — one of ``pick_f1``, ``allclose``, ``pearson``, ``rmse``.
    * ``metric_config`` — metric params (``tolerance``, ``rtol``/``atol``,
      ``rmse_scale``), forwarded to the metric.

    The reference value is the ``gold`` argument passed at score time, matching
    the ``json_extraction`` convention.
    """
    weights = {**_DEFAULT_STAGE_WEIGHTS, **(stage_weights or {})}
    calls = required_calls or []

    def scorer(model_output: str, gold: Any) -> float:
        code = extract_code(model_output)
        if not code:
            return 0.0
        score = weights["code"]

        if all(call in code for call in calls):
            score += weights["calls"]

        result = run_snippet(code, timeout_s=timeout_s, image=sandbox_image)
        if result.ok and artifact_key in result.artifacts:
            score += weights["runs"]
            acc = _accuracy(metric, result.artifacts[artifact_key], gold, metric_config)
            score += weights["accuracy"] * acc
        return max(0.0, min(1.0, score))

    return scorer


def make_scorer_from_spec(spec: dict[str, Any]) -> Callable[[str, Any], float]:
    """Reconstruct a scorer callable from a JSON-serializable spec.

    Recognised names: ``numerical_regression``, ``zero``. Kept separate from
    the STA/LTA dispatcher so the two suites stay decoupled; a Phase-4
    follow-up may promote a shared ``repere.scorers`` module.
    """
    name = spec["name"]
    config = dict(spec.get("config", {}))
    if name == "numerical_regression":
        return make_numerical_regression_scorer(
            artifact_key=config["artifact_key"],
            metric=config.get("metric", "allclose"),
            required_calls=config.get("required_calls"),
            stage_weights=config.get("stage_weights"),
            timeout_s=config.get("timeout_s", 60.0),
            sandbox_image=config.get("sandbox_image"),
            **{
                k: config[k]
                for k in ("tolerance", "rtol", "atol", "rmse_scale")
                if k in config
            },
        )
    if name == "zero":
        return lambda _out, _gold: 0.0
    raise ValueError(f"unknown scorer name: {name!r}")
