"""Ridgecrest synthetic STA/LTA suite (Family 2 / detection).

One suite over `cases.yaml` — synthetic detection cases derived from a real
2019 M7.1 Ridgecrest waveform by deterministic + seeded transforms (see
`scripts/build_synthetic_stalta.py`).

Each case asks the model to **write an STA/LTA detector**; the sandbox injects
the waveform, runs the code, and grades the onsets it reports via
`record(picks=[...])` with `stalta_code` (pick_f1). The eval turns on real
domain knowledge: a naive `trigger_onset` re-triggers on the coda and tanks
precision, so a correct answer must decluster (see the `stalta-detection`
skill). Negative cases (noise only) are first-class — the correct answer is `[]`.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import yaml

from frugalmind import DenolleGroupSuite, TaskKind
from frugalmind.export import BenchmarkRow

from .scorers import make_scorer_from_spec

_DEFAULT_CASES = Path(__file__).parent / "cases.yaml"
CASES_PATH = Path(os.environ.get("FM_SYNTH_STALTA_CASES", _DEFAULT_CASES))

VALID_SPLITS = ("validation", "test")


def _resolve_split(split: str | None) -> str | None:
    if split is None:
        env = os.environ.get("FM_SYNTH_STALTA_SPLIT")
        if env in (None, "", "all"):
            return None
        split = env
    if split not in VALID_SPLITS:
        raise ValueError(f"split must be one of {VALID_SPLITS} or None; got {split!r}")
    return split


def _load(split: str | None = None) -> tuple[dict, list[dict]]:
    if not CASES_PATH.exists():
        raise FileNotFoundError(
            f"{CASES_PATH} not found. Run "
            "`pixi run -e full python scripts/build_synthetic_stalta.py` first."
        )
    doc = yaml.safe_load(CASES_PATH.read_text())
    meta, cases = doc.get("meta", {}), doc["cases"]
    for c in cases:
        for k in ("id", "waveform", "onsets_s", "sampling_rate", "split", "visibility"):
            if k not in c:
                raise ValueError(f"case {c.get('id')!r} missing key {k!r}")
    split = _resolve_split(split)
    if split is not None:
        cases = [c for c in cases if c["split"] == split]
    return meta, cases


class SyntheticSTALTASuite(DenolleGroupSuite):
    """Waveform + STA/LTA params -> reported onset times, scored by pick_f1."""

    # The model must WRITE the detector; the sandbox runs it. Pasting ~1000 raw
    # samples into the prompt and asking an LLM to execute STA/LTA in its head is
    # not a solvable task (a live 7B run scored 0 on every item and replied "what
    # would you like me to do with these numbers?"), and it is not what we want
    # from a coding agent anyway.
    task_kind = TaskKind.CODE_GENERATION
    dataset_id = "synthetic_stalta"
    suite_id = "ridgecrest_detection"
    version = "v0.2"

    def __init__(self, *, split: str | None = None) -> None:
        self.split = _resolve_split(split)

    def _cases(self) -> list[dict]:
        return _load(self.split)[1]

    def _compose(self, c: dict) -> tuple[str, Any, dict, dict]:
        sr = c["sampling_rate"]
        dur = c["npts"] / sr
        prompt = (
            "Write Python that detects seismic events with a classic STA/LTA "
            "detector.\n\n"
            "Two variables are ALREADY DEFINED in your environment — do not "
            "redefine them:\n"
            f"  waveform : list of {c['npts']} floats (vertical component)\n"
            f"  fs       : sampling rate in Hz ({sr:g})  -> ~{dur:.0f} s of data\n\n"
            f"Use STA={c['sta_s']:g} s, LTA={c['lta_s']:g} s, trigger-on ratio "
            f"{c['thr_on']:g}, trigger-off {c['thr_off']:g}.\n\n"
            "Compute the trigger ONSET times in seconds from the start of the "
            "record, and report them by calling:\n"
            "    record(picks=[...])\n"
            "`record` is provided by the harness. numpy and obspy are available "
            "(e.g. obspy.signal.trigger.classic_sta_lta and trigger_onset). "
            "If no event is present, call record(picks=[]).\n\n"
            "Return only a single ```python code block."
        )
        gold = list(c["onsets_s"])
        scorer_spec = {
            "name": "stalta_code",
            "config": {
                "waveform": list(c["waveform"]),
                "fs": float(sr),
                "tolerance_s": c.get("onset_tolerance_s", 1.5),
            },
        }
        meta = {
            "case_id": c["id"],
            "transform": c.get("transform"),
            "expected_detection": c["expected_detection"],
        }
        return prompt, gold, scorer_spec, meta

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for c in self._cases():
            prompt, gold, scorer_spec, _ = self._compose(c)
            yield (prompt, gold, make_scorer_from_spec(scorer_spec))

    def export_rows(self) -> Iterable[BenchmarkRow]:
        for c in self._cases():
            prompt, gold, scorer_spec, meta = self._compose(c)
            yield BenchmarkRow(
                id=f"{self.dataset_id}/{self.suite_id}/{c['id']}",
                dataset_id=self.dataset_id,
                suite_id=self.suite_id,
                version=self.version,
                task_kind=self.task_kind.value,
                split=c["split"],
                visibility=c["visibility"],
                prompt=prompt,
                gold=gold,
                scorer_spec=scorer_spec,
                metadata=meta,
            )


ALL_SUITES = (SyntheticSTALTASuite,)
