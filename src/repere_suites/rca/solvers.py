"""Solvers used by the RCA runner besides Inspect's ``generate``.

``scripted``   replays a canned model output per sample id from a directory.
               Used for the harness self-test (a known-good answer must score
               1.0 and a known-bad answer must score 0.0 before any model is
               run; ABC items T.8, T.9, O.d.1) and for offline CI.
``do_nothing`` returns an empty completion. This is the do-nothing baseline
               (ABC R.13; "AI agents that matter" trivial baselines) and must
               appear on every leaderboard.

Both are Inspect ``@solver`` factories and therefore need the ``[eval]`` extra.
"""

from __future__ import annotations

from pathlib import Path

from inspect_ai.model import ModelOutput
from inspect_ai.solver import Generate, Solver, TaskState, solver


@solver
def scripted(outputs_dir: str) -> Solver:
    """Replay ``<outputs_dir>/<sample_id>.md`` as the model completion.

    A missing file yields an empty completion (scored like do-nothing) and a
    note in ``state.metadata['scripted_missing']`` so the runner can flag it.
    """
    root = Path(outputs_dir)

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        path = root / f"{state.sample_id}.md"
        if path.is_file():
            text = path.read_text(encoding="utf-8")
        else:
            text = ""
            state.metadata["scripted_missing"] = str(path)
        state.output = ModelOutput.from_content(model="scripted", content=text)
        return state

    return solve


@solver
def do_nothing() -> Solver:
    """Return an empty completion without calling any model."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        state.output = ModelOutput.from_content(model="do_nothing", content="")
        return state

    return solve


__all__ = ["do_nothing", "scripted"]
