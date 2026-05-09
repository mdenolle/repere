"""
Five EvalSuite subclasses, one per TaskKind in the STA/LTA pipeline.

All five share a single canonical truth set (events.yaml) and emit items derived
from it. Adding an event to events.yaml adds 5 graded items automatically.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


VALID_SPLITS = ("validation", "test")
VALID_VISIBILITIES = ("public", "private")


def _resolve_split(split: str | None) -> str | None:
    """Honour FM_STALTA_SPLIT when caller passed nothing; validate when present."""
    if split is None:
        env = os.environ.get("FM_STALTA_SPLIT")
        if env in (None, "", "all"):
            return None
        split = env
    if split not in VALID_SPLITS:
        raise ValueError(
            f"split must be one of {VALID_SPLITS} or None; got {split!r}"
        )
    return split


def _resolve_visibility(visibility: str | None) -> str | None:
    if visibility is None:
        return None
    if visibility not in VALID_VISIBILITIES:
        raise ValueError(
            f"visibility must be one of {VALID_VISIBILITIES} or None; got {visibility!r}"
        )
    return visibility


_FRAC_RE = re.compile(r"(\.\d+)(?=([+-]\d{2}:?\d{2}|Z|$))")


# ---------------------------------------------------------------------------
# Cutoff-date policy
#
# `cutoff_date` is the date past which a retrieval-augmented agent must not
# query (catalogs, papers, network status pages). It anchors the validity of
# a benchmark item against future world updates: a model that uses fresher
# information than it would have had at the time is cheating, even if the
# answer is correct.
#
# Default rule (applies when an event omits the field):
#   - Positive cases (`expected_detection: true`):  origin_time + 7 days
#       — analysts need ~1 week to publish a definitive catalog entry.
#   - Negative cases (`expected_detection: false`): origin_time - 1 day
#       — quiet windows must stay quiet under any future re-cataloguing.
# ---------------------------------------------------------------------------

DEFAULT_POSITIVE_CUTOFF_DAYS = 7
DEFAULT_NEGATIVE_CUTOFF_DAYS = -1


def default_cutoff_date(event: dict) -> str:
    """Compute the default `cutoff_date` for an event, as `YYYY-MM-DD`.

    Pure function — does not mutate `event`. Used by `_load_events` to fill
    in events that omit the field; callers can also use it directly.
    """
    if "origin_time" not in event:
        raise ValueError("event must include `origin_time` to compute cutoff_date")
    t0 = parse_origin_time(event["origin_time"])
    delta_days = (
        DEFAULT_POSITIVE_CUTOFF_DAYS
        if event.get("expected_detection", True)
        else DEFAULT_NEGATIVE_CUTOFF_DAYS
    )
    return (t0 + timedelta(days=delta_days)).date().isoformat()


def _normalise_cutoff_date(value: Any) -> str:
    """Convert a YAML date or string into `YYYY-MM-DD`.

    PyYAML hands back `datetime.date` for unquoted `2001-02-28`, and `str` for
    quoted strings. Normalise both shapes so downstream code only sees strings.
    """
    if isinstance(value, str):
        # Validate the shape; tolerate trailing whitespace.
        s = value.strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            raise ValueError(f"cutoff_date must be `YYYY-MM-DD`; got {value!r}")
        return s
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "isoformat"):  # datetime.date
        return value.isoformat()
    raise ValueError(f"cutoff_date must be a date or YYYY-MM-DD string; got {value!r}")


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


def _load_events(
    path: Path = EVENTS_PATH,
    *,
    split: str | None = None,
    visibility: str | None = None,
) -> list[dict]:
    """Load and validate the events file, optionally filtered by split/visibility.

    `split=None` (default) returns every event. `split="validation"` and
    `split="test"` filter to those subsets. The `FM_STALTA_SPLIT` environment
    variable supplies a default when no `split` is passed; set it to "all"
    or unset it to disable.

    `visibility` works the same way for public vs private events.
    """
    split = _resolve_split(split)
    visibility = _resolve_visibility(visibility)

    with open(path) as f:
        data = yaml.safe_load(f)
    events = data.get("events", [])
    for ev in events:
        eid = ev.get("id", "<unknown>")

        # Top-level fields read by at least one suite or by the loader itself.
        for required in (
            "id",
            "category",
            "label",
            "origin_time",
            "expected_detection",
            "recommended_stations",
            "suggested_window_min",
            "stalta_params",
            "split",
            "visibility",
        ):
            if required not in ev:
                raise ValueError(
                    f"Event {eid!r} missing required key {required!r}"
                )

        # Nested fields read by STALTATriggerCodeSuite.
        if not isinstance(ev["stalta_params"], dict):
            raise ValueError(
                f"Event {eid!r}: stalta_params must be a mapping; "
                f"got {type(ev['stalta_params']).__name__}"
            )
        for sta_key in ("sta", "lta", "on_thresh", "off_thresh"):
            if sta_key not in ev["stalta_params"]:
                raise ValueError(
                    f"Event {eid!r}: stalta_params missing required key {sta_key!r}"
                )

        # Nested fields read by every suite that names a station.
        if not isinstance(ev["recommended_stations"], list) or not ev["recommended_stations"]:
            raise ValueError(
                f"Event {eid!r}: recommended_stations must be a non-empty list"
            )
        for i, st in enumerate(ev["recommended_stations"]):
            if not isinstance(st, dict):
                raise ValueError(
                    f"Event {eid!r}: recommended_stations[{i}] must be a mapping"
                )
            for st_key in ("network", "station", "location", "channel"):
                if st_key not in st:
                    raise ValueError(
                        f"Event {eid!r}: recommended_stations[{i}] missing key {st_key!r}"
                    )

        if ev["split"] not in VALID_SPLITS:
            raise ValueError(
                f"Event {eid!r}: split must be one of {VALID_SPLITS}, "
                f"got {ev['split']!r}"
            )
        if ev["visibility"] not in VALID_VISIBILITIES:
            raise ValueError(
                f"Event {eid!r}: visibility must be one of "
                f"{VALID_VISIBILITIES}, got {ev['visibility']!r}"
            )

        # cutoff_date: fill from default rule if missing; normalise format if present.
        if "cutoff_date" in ev and ev["cutoff_date"] is not None:
            ev["cutoff_date"] = _normalise_cutoff_date(ev["cutoff_date"])
        else:
            ev["cutoff_date"] = default_cutoff_date(ev)
    if split is not None:
        events = [ev for ev in events if ev["split"] == split]
    if visibility is not None:
        events = [ev for ev in events if ev["visibility"] == visibility]
    return events


class _SplitAwareSuite(DenolleGroupSuite):
    """Mixin: filters events by ``split`` and ``visibility`` at items() time.

    All five STA/LTA suites accept the same two keyword args. Defaults to
    "no filter"; set the env var ``FM_STALTA_SPLIT`` for a process-wide default.
    """

    def __init__(
        self,
        *,
        split: str | None = None,
        visibility: str | None = None,
    ) -> None:
        self.split = _resolve_split(split)
        self.visibility = _resolve_visibility(visibility)

    def _events(self) -> list[dict]:
        return _load_events(split=self.split, visibility=self.visibility)


class STALTAIntentExtractionSuite(_SplitAwareSuite):
    """Natural-language request to structured FDSN query."""

    task_kind = TaskKind.EXTRACTION

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        from datetime import timedelta

        for ev in self._events():
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
                f"Suggested window: ±{ev['suggested_window_min'] / 2:g} minutes around origin.\n"
                f"Cutoff date for catalog/metadata queries: {ev['cutoff_date']}\n\n"
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


class STALTAFetchCodeSuite(_SplitAwareSuite):
    """Structured request to ObsPy waveform-fetching code."""

    task_kind = TaskKind.CODE_GENERATION

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for ev in self._events():
            station = ev["recommended_stations"][0]
            prompt = (
                "Write a Python snippet using ObsPy that fetches a waveform "
                "from the EarthScope FDSN service.\n\n"
                f"  network = {station['network']!r}\n"
                f"  station = {station['station']!r}\n"
                f"  location = {station['location']!r}\n"
                f"  channel = {station['channel']!r}\n"
                f"  starttime = '{ev['origin_time']}' minus {ev['suggested_window_min'] / 2:g} minutes\n"
                f"  endtime   = '{ev['origin_time']}' plus  {ev['suggested_window_min'] / 2:g} minutes\n"
                f"  cutoff_date = '{ev['cutoff_date']}'  # do not query catalog/inventory after this date\n\n"
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


class STALTATriggerCodeSuite(_SplitAwareSuite):
    """Loaded ObsPy stream to STA/LTA trigger code."""

    task_kind = TaskKind.CODE_GENERATION

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for ev in self._events():
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
                f"Cutoff date for any catalog/metadata reference: {ev['cutoff_date']}.\n"
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


class STALTAPlotSuite(_SplitAwareSuite):
    """Plot waveform and STA/LTA triggers against approved goldens."""

    task_kind = TaskKind.PLOTTING

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        golden_dir = Path(
            os.environ.get("FM_STALTA_GOLDEN_DIR", Path(__file__).parent / "data" / "golden")
        )
        for ev in self._events():
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
                "parameters are obvious.\n"
                f"Cutoff date for any catalog/metadata reference: {ev['cutoff_date']}."
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


class STALTAReportSuite(_SplitAwareSuite):
    """STA/LTA detection result to concise technical report."""

    task_kind = TaskKind.REPORT_DRAFTING

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for ev in self._events():
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
                    f"Detection result:\n{detection_summary}\n\n"
                    f"Cutoff date for catalog cross-reference: {ev['cutoff_date']}."
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
                    f"Detection result:\n{detection_summary}\n\n"
                    f"Cutoff date for catalog cross-reference: {ev['cutoff_date']}."
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
