"""Pipeline-regression suite (Family 2: coding agents, data-out).

The model drives a real scientific pipeline (seisbench, noisepy, codameter)
and reports a numeric result via ``record(...)``; the ``numerical_regression``
scorer compares it to a reference with a numeric tolerance and no LLM in the
loop (tier T1 on the scorability spectrum). See
``docs/numerical_regression_scorer.md``.

The InspectAI tasks live in ``inspect_tasks.py`` and require the optional
``inspect-ai`` extra; the scorer and suite here have no such dependency.
"""

from __future__ import annotations

from . import items, scorers
from .items import ALL_SUITES, PIPELINES_PATH, PipelineRegressionSuite

__all__ = [
    "ALL_SUITES",
    "PIPELINES_PATH",
    "PipelineRegressionSuite",
    "items",
    "scorers",
]
