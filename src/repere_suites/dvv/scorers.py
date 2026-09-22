"""Scorer registry for the dv/v suite (Repère family convention).

The scoring logic lives in codameter (it regenerates the hidden synthetic and
runs the pipeline), so this re-exports it. Recognised names: ``dvv_recovery``
and ``dvv_series_regression``. Requires ``codameter`` at scoring time.
"""
from __future__ import annotations

from typing import Any, Callable


def make_scorer_from_spec(spec: dict) -> Callable[[str, Any], float]:
    # ``codameter.frugalmind`` is codameter's own module name upstream, not a
    # leftover of the Repère rename -- it is codameter's to rename, not ours.
    # Do not let a blanket frugalmind -> repere substitution touch this line.
    from codameter.frugalmind import make_scorer_from_spec as _impl
    return _impl(spec)


__all__ = ["make_scorer_from_spec"]
