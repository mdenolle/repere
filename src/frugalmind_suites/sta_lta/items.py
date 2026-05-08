"""
Five EvalSuite subclasses, one per TaskKind in the STA/LTA pipeline.

All five share a single canonical truth set (events.yaml) and emit items derived
from it. Adding an event to events.yaml adds 5 graded items automatically.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
import os
import re

import yaml

from frugalmind import DenolleGroupSuite, TaskKind

from .scorers import (
    make_code_execution_scorer,
    make_json_extraction_scorer,
    make_plot_ssim_scorer,
    make_report_scorer,
)


_DEFAULT_EVENTS = Path(__file__).parent / "events.yaml"
EVENTS_PATH = Path(os.environ.get("FM_STALTA_EVENTS", _DEFAULT_EVENTS))


_FRAC_RE = re.compile(r"(\.\d+)(?=([+-]\d{2}:?\d{2}|Z|$))")


def parse_origin_time(value: str) -> datetime:
    """Robust ISO-8601 parser tolerating 1-9 fractional digits and missing tz.

    `datetime.fromisoformat` on Python 3.10 only accepts 0/3/6 fractional digits;
    `events.yaml` uses 1-digit fractions like 'YYYY-MM-DDTHH:MM:SS.8'. Pad to 6.
    """
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    def _pad(match: re.Match) -> str:
        frac = match.group(1)[1:]  # strip leading '.'
        frac = (frac + "000000")[:6]
        return f".{frac}"

    text = _FRAC_RE.sub(_pad, text)
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _load_events(path: Path = EVENTS_PATH) -> list[dict]:
    """Load and validate the events file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    events = data.get("events", [])
    for ev in events:
        for required in (
            "id",
            "category",
            "expected_detection",
            "recommended_stations",
            "suggested_window_min",
        ):
            if required not in ev:
                raise ValueError(
                    f"Event {ev.get('id', '<unknown>')} missing required key {required!r}"
                )
    return events


class STALTAIntentExtractionSuite(DenolleGroupSuite):
    """Natural-language request to structured FDSN query."""

    task_kind = TaskKind.EXTRACTION

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        from datetime import timedelta

        for ev in _load_events():
            station = ev["recommended_stations"][0]
            t0_str = ev["origin_time"]
            t0 = parse_origin_time(t0_str)
            half = timedelta(minutes=ev["suggested_window_min"] / 2)
            start, end = (t0 - half).isoformat(), (t0 + half).isoformat()

            prompt = (
                "Extract a JSON object describing the FDSN waveform request "
                "for this analysis task:\n\n"
                f"Task: {ev['label']}\n"
                f"Origin time (UTC): {t0_str}\n"
                f"Suggested station: {station['network']}.{station['station']}.{station['location']}.{station['channel']}\n"
                f"Suggested window: ±{ev['suggested_window_min'] / 2:g} minutes around origin.\n\n"
                "Return ONLY a JSON object with keys: network, station, location, channel, "
                "starttime, endtime. Use ISO-8601 timestamps."
            )
            gold = {
                "network": station["network"],
                "station": station["station"],
                "location": station["location"],
                "channel": station["channel"],
                "starttime": start,
                "endtime": end,
            }
            scorer = make_json_extraction_scorer(
                required_fields=list(gold),
                field_tolerances={"starttime": 5.0, "endtime": 5.0},
            )
            yield (prompt, gold, scorer)


class STALTAFetchCodeSuite(DenolleGroupSuite):
    """Structured request to ObsPy waveform-fetching code."""

    task_kind = TaskKind.CODE_GENERATION

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for ev in _load_events():
            station = ev["recommended_stations"][0]
            prompt = (
                "Write a Python snippet using ObsPy that fetches a waveform "
                "from the EarthScope FDSN service.\n\n"
                f"  network = {station['network']!r}\n"
                f"  station = {station['station']!r}\n"
                f"  location = {station['location']!r}\n"
                f"  channel = {station['channel']!r}\n"
                f"  starttime = '{ev['origin_time']}' minus {ev['suggested_window_min'] / 2:g} minutes\n"
                f"  endtime   = '{ev['origin_time']}' plus  {ev['suggested_window_min'] / 2:g} minutes\n\n"
                "After fetching, call record(n_traces=len(st), "
                "sampling_rate=st[0].stats.sampling_rate). `record` is a helper provided "
                "by the test harness that captures values for scoring."
            )
            gold = {"event_id": ev["id"]}
            scorer = make_code_execution_scorer(
                required_calls=["Client", ".get_waveforms"],
                expected_artifact_keys=["n_traces", "sampling_rate"],
                artifact_predicates={
                    "n_traces": lambda x: isinstance(x, int) and x >= 1,
                    "sampling_rate": lambda x: isinstance(x, (int, float)) and x > 0,
                },
                timeout_s=60.0,
            )
            yield (prompt, gold, scorer)


class STALTATriggerCodeSuite(DenolleGroupSuite):
    """Loaded ObsPy stream to STA/LTA trigger code."""

    task_kind = TaskKind.CODE_GENERATION

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for ev in _load_events():
            p = ev["stalta_params"]
            prompt = (
                "Assume `st` is an `obspy.Stream` already loaded into memory. "
                "Write a Python snippet that:\n"
                "  1. Detrends and filters `st` (1-20 Hz bandpass).\n"
                f"  2. Runs classic recursive STA/LTA on st[0] with sta={p['sta']}s, "
                f"lta={p['lta']}s.\n"
                f"  3. Picks triggers using on_thresh={p['on_thresh']}, "
                f"off_thresh={p['off_thresh']}.\n"
                "  4. Calls record(n_triggers=<int>, first_trigger_sample=<int or None>) "
                "so the test harness can verify the result.\n\n"
                "Use obspy.signal.trigger.classic_sta_lta and trigger_onset."
            )
            gold = {"event_id": ev["id"], "expected_detection": ev["expected_detection"]}
            if ev["expected_detection"]:

                def trig_pred(x):
                    return isinstance(x, int) and x >= 1
            else:

                def trig_pred(x):
                    return isinstance(x, int) and x == 0

            scorer = make_code_execution_scorer(
                required_calls=["classic_sta_lta", "trigger_onset"],
                expected_artifact_keys=["n_triggers"],
                artifact_predicates={"n_triggers": trig_pred},
                timeout_s=30.0,
            )
            yield (prompt, gold, scorer)


class STALTAPlotSuite(DenolleGroupSuite):
    """Plot waveform and STA/LTA triggers against approved goldens."""

    task_kind = TaskKind.PLOTTING

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        golden_dir = Path(
            os.environ.get("FM_STALTA_GOLDEN_DIR", Path(__file__).parent / "data" / "golden")
        )
        for ev in _load_events():
            golden = golden_dir / f"{ev['id']}.png"
            station = ev["recommended_stations"][0]
            prompt = (
                "Given an `obspy.Stream` named `st` (already loaded), produce "
                "a matplotlib figure that:\n"
                "  - shows the seismogram for st[0] in the top panel,\n"
                "  - shows the STA/LTA characteristic function in the bottom panel,\n"
                "  - overlays vertical lines at the trigger onsets,\n"
                f"  - includes a clear title with the station ({station['network']}."
                f"{station['station']}) and event label ({ev['label']}).\n\n"
                "Save the figure as 'plot.png' in the current working directory. "
                "Use sta=2s, lta=10s, on=3.5, off=1.5 unless event-specific "
                "parameters are obvious."
            )
            gold = {"event_id": ev["id"], "golden_path": str(golden)}
            if not golden.exists():

                def missing_golden_scorer(out, g, _path=str(golden)):
                    return 0.0

                yield (prompt, gold, missing_golden_scorer)
                continue
            scorer = make_plot_ssim_scorer(
                golden_png_path=str(golden),
                ssim_threshold=0.85,
                timeout_s=60.0,
            )
            yield (prompt, gold, scorer)


class STALTAReportSuite(DenolleGroupSuite):
    """STA/LTA detection result to concise technical report."""

    task_kind = TaskKind.REPORT_DRAFTING

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for ev in _load_events():
            station = ev["recommended_stations"][0]
            stationstr = f"{station['network']}.{station['station']}"

            if ev["expected_detection"]:
                detection_summary = (
                    f"STA/LTA on {stationstr} channel {station['channel']} "
                    f"reported triggers near {ev['origin_time']}."
                )
                prompt = (
                    "Write a one-paragraph technical report describing the "
                    "detection result below. Mention the origin time, the station, "
                    "and any inferred magnitude. Be precise.\n\n"
                    f"Detection result:\n{detection_summary}"
                )
                if ev["category"] == "quarry_blast":
                    scorer = make_report_scorer(
                        expected_detection=True,
                        origin_time_iso=ev["origin_time"],
                        magnitude=ev.get("magnitude"),
                        required_terms=["blast"],
                        forbidden_terms=["tectonic earthquake", "earthquake of magnitude"],
                    )
                else:
                    scorer = make_report_scorer(
                        expected_detection=True,
                        origin_time_iso=ev["origin_time"],
                        origin_time_tolerance_s=60.0,
                        magnitude=ev.get("magnitude"),
                        magnitude_tolerance=0.7,
                    )
            else:
                detection_summary = (
                    f"STA/LTA on {stationstr} channel {station['channel']} "
                    "during the test window: 0 triggers above threshold."
                )
                prompt = (
                    "Write a one-paragraph technical report describing the "
                    "result below. Be precise about what was and was not observed.\n\n"
                    f"Detection result:\n{detection_summary}"
                )
                scorer = make_report_scorer(
                    expected_detection=False,
                    required_terms=["no events"],
                    forbidden_terms=["detected an earthquake", "tectonic event"],
                )
            gold = {"event_id": ev["id"], "category": ev["category"]}
            yield (prompt, gold, scorer)


ALL_SUITES = [
    STALTAIntentExtractionSuite(),
    STALTAFetchCodeSuite(),
    STALTATriggerCodeSuite(),
    STALTAPlotSuite(),
    STALTAReportSuite(),
]
