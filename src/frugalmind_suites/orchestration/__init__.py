"""Orchestration suite (Family 3): non-linear subagent workflows.

Scores the DAG of subagent invocations an orchestrator produces against a
reference DAG (node F1 + edge F1 + frugality), deterministically. Frugality is
a first-class scored dimension because orchestrators are where fan-out cost
explodes. See ``docs/orchestration_scorer.md``.

InspectAI tasks live in ``inspect_tasks.py`` (optional ``inspect-ai`` extra);
the scorer and suite here have no such dependency.
"""

from __future__ import annotations

from . import items, scorers
from .items import ALL_SUITES, TASKS_PATH, OrchestrationSuite

__all__ = [
    "ALL_SUITES",
    "TASKS_PATH",
    "OrchestrationSuite",
    "items",
    "scorers",
]
