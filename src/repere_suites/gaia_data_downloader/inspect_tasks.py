"""Inspect AI task definitions for the gaia_data_downloader suite.

Usage
-----
    inspect eval src/repere_suites/gaia_data_downloader/inspect_tasks.py \
        --model anthropic/claude-sonnet-4-6
    inspect eval src/repere_suites/gaia_data_downloader/inspect_tasks.py@gaia_dl_easy \
        --model openai/gpt-4o

This file is part of Repère's Phase 2.1 (adopt InspectAI as substrate)
roadmap item, applied to the GAIA suite. Three tasks are defined:

  * gaia_dl_easy
  * gaia_dl_medium
  * gaia_dl_hard

Each task:
  1. Loads from tasks.yaml (filtered by difficulty + split honoring REPERE_GAIA_SPLIT).
  2. Runs the gaia-data-downloader agent in a Docker sandbox.
  3. Scores with execution_pass + structural_checksum + trajectory_quality
     + tool_efficiency.
  4. Emits cost-per-task in USD using the AstaBench frozen price table.

This file is a STUB. To run for real you need:
  * ``pip install inspect-ai`` (or add ``inspect-ai`` to the ``[eval]`` extra
    in pyproject.toml).
  * The sandbox image ``ghcr.io/uw-ssec/gaia-eval:0.1.0`` published.
  * The gaia-data-downloader agent installed in the sandbox.
"""

from __future__ import annotations

import os
from typing import Any

import yaml

from . import TASKS_PATH


VALID_SPLITS = ("validation", "test")


def _resolve_split(split: str | None) -> str | None:
    if split is None:
        env = os.environ.get("REPERE_GAIA_SPLIT")
        if env in (None, "", "all"):
            return None
        split = env
    if split not in VALID_SPLITS:
        raise ValueError(f"split must be one of {VALID_SPLITS} or None; got {split!r}")
    return split


def _load_tasks(difficulty: str | None = None, split: str | None = None) -> list[dict[str, Any]]:
    if not TASKS_PATH.exists():
        raise FileNotFoundError(
            f"{TASKS_PATH} not found. Run "
            f"`python scripts/sync_gaia_tasks.py --release v0.1.0` first."
        )
    data = yaml.safe_load(TASKS_PATH.read_text())
    tasks = data["tasks"]
    split = _resolve_split(split)
    if split is not None:
        tasks = [t for t in tasks if t["split"] == split]
    if difficulty is not None:
        tasks = [t for t in tasks if t["difficulty"] == difficulty]
    return tasks


def _task_to_sample(t: dict[str, Any]):  # -> Sample (when inspect-ai is installed)
    """Map a canonical task dict to an Inspect AI Sample."""
    # from inspect_ai.dataset import Sample
    # return Sample(
    #     id=t["id"],
    #     input=t["prompt"],
    #     metadata={
    #         "expected_files": t["expected_files"],
    #         "expected_tools": t["expected_tools"],
    #         "required_cli_args": t["required_cli_args"],
    #         "checksum_strategy": t["checksum_strategy"],
    #         "domain": t["domain"],
    #         "difficulty": t["difficulty"],
    #         "data_source_url": t["data_source_url"],
    #         "timeout_s": t["timeout_s"],
    #     },
    #     sandbox=("docker", _sandbox_compose(t)),
    # )
    raise NotImplementedError("Uncomment after `pip install inspect-ai`.")


def _sandbox_compose(task: dict[str, Any]) -> str:
    """Render the per-task docker-compose spec for the Inspect AI sandbox."""
    raise NotImplementedError("Wire to ghcr.io/uw-ssec/gaia-eval:0.1.0")


# ----------------------- Scorers ------------------------------------------- #
def execution_pass_scorer():
    """Run the produced download.py inside the sandbox; check expected files exist."""
    raise NotImplementedError(
        "Implementation: write the agent's final code to /work/download.py inside "
        "the sandbox, exec it with the required_cli_args, then check "
        "expected_files globs against the produced filesystem."
    )


def trajectory_quality_scorer():
    """LLM-judge over the tool-call trace."""
    raise NotImplementedError


def tool_efficiency_scorer():
    """Jaccard between observed tool calls and expected_tools."""
    raise NotImplementedError


# ----------------------- Tasks --------------------------------------------- #
def _build_task(difficulty: str):
    tasks = _load_tasks(difficulty=difficulty)
    samples = [_task_to_sample(t) for t in tasks]
    # from inspect_ai import Task
    # from inspect_ai.solver import system_message, use_tools, generate
    # from inspect_ai.tool import bash
    # return Task(
    #     dataset=samples,
    #     solver=[
    #         system_message(
    #             "You are the gaia-data-downloader agent. Produce a single "
    #             "Python script named download.py that uses pixi-managed "
    #             "dependencies and exposes the required CLI args."
    #         ),
    #         use_tools([bash()]),
    #         generate(),
    #     ],
    #     scorer=[
    #         execution_pass_scorer(),
    #         trajectory_quality_scorer(),
    #         tool_efficiency_scorer(),
    #     ],
    # )
    raise NotImplementedError(f"Build Inspect Task for {difficulty} ({len(samples)} samples).")


# @task
def gaia_dl_easy():
    return _build_task("easy")


# @task
def gaia_dl_medium():
    return _build_task("medium")


# @task
def gaia_dl_hard():
    return _build_task("hard")
