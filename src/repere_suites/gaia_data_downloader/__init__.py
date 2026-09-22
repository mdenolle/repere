"""GAIA data-downloader golden suite for Repère.

Evaluates the `gaia-data-downloader` agent (defined in
``uw-ssec/rse-plugins/community-plugins/gaia-data-downloader``) on 30
multi-domain coding tasks. Authoring surface is GitHub issues on
``uw-ssec/gaia-agentic-ai`` labelled ``golden-task``; see ``provenance.yaml``.

This module is intentionally light at v0.1 — the InspectAI tasks live in
``inspect_tasks.py`` and require the optional ``inspect-ai`` extra.
"""

from __future__ import annotations

from pathlib import Path

TASKS_PATH = Path(__file__).parent / "tasks.yaml"
PROVENANCE_PATH = Path(__file__).parent / "provenance.yaml"

__all__ = ["TASKS_PATH", "PROVENANCE_PATH"]
