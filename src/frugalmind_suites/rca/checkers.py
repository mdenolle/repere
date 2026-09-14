"""Deterministic checkers for T2 (execution-verified) RCA records.

A checker is a pure function ``(exec_result, args) -> CheckOutcome`` that
never calls a model and never touches the network. It is addressed from a
record by ``scoring.checker.module`` / ``scoring.checker.function`` and
rebuilt at scoring time by :func:`resolve_checker`, so a third party holding
the record and the sandbox output can reproduce the score without this
package's Python.

Scoring is staged (frugalmind convention, ``docs/numerical_regression_scorer.md``):

    code    a code block was extracted from the model output
    runs    the sandbox run finished with ok=True and recorded every artifact key
    correct the checker's own comparison

Stage weights default to 0.1 / 0.2 / 0.7 and may be overridden per record via
``scoring.checker.stage_weights``. The ``correct`` stage is graded in [0, 1];
the other two are binary.
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

DEFAULT_STAGE_WEIGHTS = {"code": 0.1, "runs": 0.2, "correct": 0.7}


@dataclass(frozen=True)
class CheckOutcome:
    """Result of a checker on one sample."""

    correct: float  # in [0, 1]
    explanation: str
    details: dict[str, Any] = field(default_factory=dict)


CheckerFn = Callable[[Any, Mapping[str, Any]], CheckOutcome]


def resolve_checker(spec: Mapping[str, Any]) -> CheckerFn:
    """Import ``spec['module']`` and return ``spec['function']``.

    Only modules under ``frugalmind_suites.rca`` are importable through this
    path; a record that points elsewhere is rejected so a hidden-split record
    cannot smuggle arbitrary code into the scorer.
    """
    module = str(spec.get("module", ""))
    if not module.startswith("frugalmind_suites.rca"):
        raise ValueError(f"checker module must live under frugalmind_suites.rca, got {module!r}")
    fn_name = str(spec.get("function", ""))
    mod = importlib.import_module(module)
    fn = getattr(mod, fn_name, None)
    if fn is None or not callable(fn):
        raise ValueError(f"checker {module}:{fn_name} not found")
    return fn


def staged_score(
    *,
    code_extracted: bool,
    ran_ok: bool,
    artifacts: Mapping[str, Any],
    artifact_keys: list[str],
    outcome: CheckOutcome | None,
    stage_weights: Mapping[str, float] | None = None,
) -> tuple[float, dict[str, Any]]:
    """Combine the three stages into one score in [0, 1]."""
    w = dict(DEFAULT_STAGE_WEIGHTS)
    if stage_weights:
        w.update({k: float(v) for k, v in stage_weights.items()})
    total = sum(w.values())
    if not math.isclose(total, 1.0, abs_tol=1e-6):
        raise ValueError(f"stage_weights must sum to 1.0, got {total}")

    recorded_all = all(k in artifacts for k in artifact_keys)
    stages = {
        "code": 1.0 if code_extracted else 0.0,
        "runs": 1.0 if (ran_ok and recorded_all) else 0.0,
        "correct": float(outcome.correct)
        if (outcome is not None and ran_ok and recorded_all)
        else 0.0,
    }
    score = sum(w[k] * stages[k] for k in stages)
    return max(0.0, min(1.0, score)), {"stages": stages, "weights": w}


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------


def _within(got: Any, want: Any, tol: Mapping[str, Any] | None) -> bool:
    if isinstance(want, str) or isinstance(got, str):
        return str(got) == str(want)
    try:
        g, wv = float(got), float(want)
    except (TypeError, ValueError):
        return got == want
    abs_tol = float((tol or {}).get("abs", 0.0))
    rel_tol = float((tol or {}).get("rel", 0.0))
    return math.isclose(g, wv, abs_tol=abs_tol, rel_tol=rel_tol)


# ---------------------------------------------------------------------------
# Checkers
# ---------------------------------------------------------------------------


def artifact_values(exec_result: Any, args: Mapping[str, Any]) -> CheckOutcome:
    """Compare every key in ``args['expected']`` with the recorded artifact.

    ``args['tolerances']`` maps a key to ``{abs, rel}``. Missing keys count as
    wrong. Score = fraction of expected keys within tolerance, or 0/1 when
    ``args['all_or_nothing']`` is true (use it for negative-case controls:
    a hallucinated gap on a clean window must not earn partial credit).
    """
    expected: Mapping[str, Any] = args.get("expected") or {}
    tolerances: Mapping[str, Any] = args.get("tolerances") or {}
    all_or_nothing = bool(args.get("all_or_nothing", False))
    artifacts: Mapping[str, Any] = getattr(exec_result, "artifacts", None) or {}
    if not expected:
        return CheckOutcome(0.0, "checker args.expected is empty")
    hits = {}
    for key, want in expected.items():
        got = artifacts.get(key, None)
        hits[key] = got is not None and _within(got, want, tolerances.get(key))
    frac = sum(hits.values()) / len(hits)
    if all_or_nothing:
        frac = 1.0 if frac == 1.0 else 0.0
    missed = [k for k, ok in hits.items() if not ok]
    return CheckOutcome(
        frac, "all keys match" if not missed else f"mismatch: {missed}", {"hits": hits}
    )


def fdsn_records(exec_result: Any, args: Mapping[str, Any]) -> CheckOutcome:
    """Checker for group 1a download tasks.

    Expects ``trace_id``, ``sampling_rate_hz``, ``n_samples`` in the recorded
    artifacts and compares them to ``args['expected']``; ``n_samples`` is
    compared within ``args['tolerance_samples']`` (default 0). All three must
    match for full credit; partial credit is the fraction matched, so a script
    that resolves the right channel but fetches the wrong window still shows
    where it went wrong in ``details``.
    """
    expected: Mapping[str, Any] = args.get("expected") or {}
    tol_n = int(args.get("tolerance_samples", 0))
    tolerances = {"n_samples": {"abs": tol_n}, "sampling_rate_hz": {"abs": 1e-6}}
    return artifact_values(exec_result, {"expected": expected, "tolerances": tolerances})


def trigger_count(exec_result: Any, args: Mapping[str, Any]) -> CheckOutcome:
    """Checker for group 1d STA/LTA tasks: number of declustered trigger onsets.

    ``args['expected_n_triggers']`` is the reference count computed by the
    pinned recipe (``frugalmind_suites.sta_lta.recipe``) on the same fixture
    with the same parameters. Exact match required; a negative case has
    ``expected_n_triggers: 0`` and any reported trigger scores 0.
    """
    artifacts: Mapping[str, Any] = getattr(exec_result, "artifacts", None) or {}
    want = args.get("expected_n_triggers")
    if want is None:
        return CheckOutcome(0.0, "expected_n_triggers is unset (TODO in the record)")
    got = artifacts.get("n_triggers")
    if got is None:
        return CheckOutcome(0.0, "n_triggers not recorded")
    ok = int(got) == int(want)
    return CheckOutcome(1.0 if ok else 0.0, f"got {got}, want {want}", {"got": got, "want": want})


__all__ = [
    "CheckOutcome",
    "DEFAULT_STAGE_WEIGHTS",
    "artifact_values",
    "fdsn_records",
    "resolve_checker",
    "staged_score",
    "trigger_count",
]
