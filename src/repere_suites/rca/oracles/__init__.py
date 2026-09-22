"""T1 oracle solvers. Addressed from records as ``module:function``.

Only modules under ``repere_suites.rca.oracles`` may be resolved, for the
same reason as checkers: a record must not be able to import arbitrary code
into the scorer.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from typing import Any

OracleFn = Callable[..., dict[str, Any]]


def resolve_oracle(spec: Mapping[str, Any]) -> OracleFn:
    solver = str(spec.get("solver", ""))
    if ":" not in solver:
        raise ValueError(f"oracle.solver must be 'module:function', got {solver!r}")
    module, fn_name = solver.split(":", 1)
    if not module.startswith("repere_suites.rca.oracles"):
        raise ValueError(
            f"oracle module must live under repere_suites.rca.oracles, got {module!r}"
        )
    mod = importlib.import_module(module)
    fn = getattr(mod, fn_name, None)
    if fn is None or not callable(fn):
        raise ValueError(f"oracle {solver} not found")
    return fn


__all__ = ["OracleFn", "resolve_oracle"]
