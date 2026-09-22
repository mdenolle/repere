"""GAIA data-downloader golden suite for Repère.

Evaluates the `gaia-data-downloader` agent (defined in
``uw-ssec/rse-plugins/community-plugins/gaia-data-downloader``) on 30
multi-domain coding tasks. Authoring surface is GitHub issues on
``uw-ssec/gaia-agentic-ai`` labelled ``golden-task``; see ``provenance.yaml``.

This module is intentionally light at v0.1 — the InspectAI tasks live in
``inspect_tasks.py`` and require the optional ``inspect-ai`` extra.
"""

from __future__ import annotations

import os
from pathlib import Path

TASKS_PATH = Path(__file__).parent / "tasks.yaml"
PROVENANCE_PATH = Path(__file__).parent / "provenance.yaml"

# `tasks.yaml` holds the PUBLIC validation partition only. The test partition
# carries each task's expected_tools, required_cli_args and expected_files
# globs -- the answers -- and several of its rows are marked
# `contamination_risk: high`, so it is neither committed nor shipped in the
# wheel. It lives in REPERE_EVAL_DATA_DIR with the other held-out partitions.
_REPO = Path(__file__).resolve().parents[3]
PRIVATE_DIR = Path(os.environ.get("REPERE_EVAL_DATA_DIR", _REPO / "data" / "private"))
HIDDEN_TASKS_PATH = PRIVATE_DIR / "gaia_data_downloader_test.yaml"

__all__ = ["TASKS_PATH", "PROVENANCE_PATH", "HIDDEN_TASKS_PATH", "PRIVATE_DIR"]
