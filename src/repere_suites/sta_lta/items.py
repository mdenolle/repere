"""
Five EvalSuite subclasses, one per TaskKind in the STA/LTA pipeline.

All five share a single canonical truth set (events.yaml) and emit items derived
from it. Adding an event to events.yaml adds 5 graded items automatically.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from repere import DenolleGroupSuite, TaskKind
from repere.export import BenchmarkRow

from .scorers import make_scorer_from_spec

_DEFAULT_EVENTS = Path(__file__).parent / "events.yaml"
EVENTS_PATH = Path(os.environ.get("REPERE_STALTA_EVENTS", _DEFAULT_EVENTS))

# --------------------------------------------------------------------------
# Public validation vs hidden test, the same split as synthetic_stalta and
# paper_workflow use.
#
# `events.yaml` (in-repo) is the PUBLIC validation split: develop against it,
# reproduce the demo board with it. It is deliberately committed.
#
# The TEST split is NOT in git and is NOT in the wheel. Its rows carry the
# answers -- expected_detection, the reference stalta_params, the station
# picks -- so committing them would publish the benchmark's gold. They live in
# REPERE_EVAL_DATA_DIR alongside the other held-out partitions; pull them with
# `scripts/pull_eval_data.py`. A benchmark whose answers ship in its own
# package measures memorisation, not capability.
# --------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[3]
PRIVATE_DIR = Path(os.environ.get("REPERE_EVAL_DATA_DIR", _REPO / "data" / "private"))
HIDDEN_EVENTS_PATH = PRIVATE_DIR / "sta_lta_test.yaml"


VALID_SPLITS = ("validation", "test")
VALID_VISIBILITIES = ("public", "private")


def _resolve_split(split: str | None) -> str | None:
    """Honour REPERE_STALTA_SPLIT when caller passed nothing; validate when present."""
    if split is None:
        env = os.environ.get("REPERE_STALTA_SPLIT")
        if env in (None, "", "all"):
            return None
        split = env
    if split not in VALID_SPLITS:
        raise ValueError(f"split must be one of {VALID_SPLITS} or None; got {split!r}")
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
# Match an unpadded H:M:S component, e.g. "23:46:0" → must become "23:46:00".
_UNPADDED_HMS_RE = re.compile(r"T(\d{1,2}):(\d{1,2}):(\d{1,2})(?=[.+\-Z]|$)")


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
    # Tolerate "YYYY/MM/DD" date separators and "YYYY-MM-DD HH:MM:SS" T-less form.
    if "/" in text[:10]:
        text = text[:10].replace("/", "-") + text[10:]
    if len(text) > 10 and text[10] == " ":
        text = text[:10] + "T" + text[11:]
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    def _pad(match: re.Match) -> str:
        frac = match.group(1)[1:]  # strip leading '.'
        frac = (frac + "000000")[:6]
        return f".{frac}"

    text = _FRAC_RE.sub(_pad, text)

    def _pad_hms(match: re.Match) -> str:
        h, m, s = match.group(1), match.group(2), match.group(3)
        return f"T{int(h):02d}:{int(m):02d}:{int(s):02d}"

    text = _UNPADDED_HMS_RE.sub(_pad_hms, text)
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _validate_events(events: list, source: Path | str) -> list[dict]:
    """Validate a list of event rows in place and return it.

    Shared by the packaged `events.yaml` and the held-out partition, so a
    malformed held-out row fails at load rather than on the run that decides
    a ranked score.
    """
    for idx, ev in enumerate(events):
        if not isinstance(ev, dict):
            raise ValueError(
                f"{source} events[{idx}] must be a mapping; got {type(ev).__name__} ({ev!r:.80})"
            )
        eid = ev.get("id", f"<unknown @ events[{idx}]>")

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
                raise ValueError(f"Event {eid!r} missing required key {required!r}")

        # Nested fields read by STALTATriggerCodeSuite.
        if not isinstance(ev["stalta_params"], dict):
            raise ValueError(
                f"Event {eid!r}: stalta_params must be a mapping; "
                f"got {type(ev['stalta_params']).__name__}"
            )
        for sta_key in ("sta", "lta", "on_thresh", "off_thresh"):
            if sta_key not in ev["stalta_params"]:
                raise ValueError(f"Event {eid!r}: stalta_params missing required key {sta_key!r}")

        # Nested fields read by every suite that names a station.
        if not isinstance(ev["recommended_stations"], list) or not ev["recommended_stations"]:
            raise ValueError(f"Event {eid!r}: recommended_stations must be a non-empty list")
        for i, st in enumerate(ev["recommended_stations"]):
            if not isinstance(st, dict):
                raise ValueError(f"Event {eid!r}: recommended_stations[{i}] must be a mapping")
            for st_key in ("network", "station", "location", "channel"):
                if st_key not in st:
                    raise ValueError(
                        f"Event {eid!r}: recommended_stations[{i}] missing key {st_key!r}"
                    )

        if ev["split"] not in VALID_SPLITS:
            raise ValueError(
                f"Event {eid!r}: split must be one of {VALID_SPLITS}, got {ev['split']!r}"
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
    return events


def _load_events(
    path: Path = EVENTS_PATH,
    *,
    split: str | None = None,
    visibility: str | None = None,
) -> list[dict]:
    """Load and validate the events file, optionally filtered by split/visibility.

    `split=None` (default) returns every event. `split="validation"` and
    `split="test"` filter to those subsets. The `REPERE_STALTA_SPLIT` environment
    variable supplies a default when no `split` is passed; set it to "all"
    or unset it to disable.

    `visibility` works the same way for public vs private events.
    """
    split = _resolve_split(split)
    visibility = _resolve_visibility(visibility)

    with open(path) as f:
        data = yaml.safe_load(f)
    events = data.get("events", [])
    if not isinstance(events, list):
        raise ValueError(f"events.yaml `events` must be a list; got {type(events).__name__}")

    # Merge the held-out partition, but only when reading the packaged file: a
    # caller that passes an explicit path wants exactly that file. The merge
    # happens after the per-row validation below, so malformed rows in the file
    # under test still produce their own error rather than tripping over the
    # hidden partition first.
    merge_hidden = Path(path) == Path(EVENTS_PATH) and HIDDEN_EVENTS_PATH.is_file()
    events = _validate_events(events, path)

    if merge_hidden:
        hidden = yaml.safe_load(HIDDEN_EVENTS_PATH.read_text()) or {}
        hidden_events = hidden.get("events", [])
        if not isinstance(hidden_events, list):
            raise ValueError(
                f"{HIDDEN_EVENTS_PATH} `events` must be a list; "
                f"got {type(hidden_events).__name__}"
            )
        # Same validation as the public rows: a held-out row that fails it would
        # otherwise only blow up on the run that decides a ranked score.
        hidden_events = _validate_events(hidden_events, HIDDEN_EVENTS_PATH)
        clash = {e["id"] for e in events} & {e["id"] for e in hidden_events}
        if clash:
            raise ValueError(
                f"event id(s) {sorted(clash)} appear in both {path} and "
                f"{HIDDEN_EVENTS_PATH}; an id belongs to exactly one partition"
            )
        events = events + hidden_events

    if split == "test" and not any(ev["split"] == "test" for ev in events):
        raise FileNotFoundError(
            "the hidden test split is not available locally.\n"
            f"  expected: {HIDDEN_EVENTS_PATH}\n"
            "  pull it (requires access to the gated dataset):\n"
            "      pixi run -e full python scripts/pull_eval_data.py\n"
            "  Ranked scores are computed on the hidden split only; the public "
            "`validation` split is for development."
        )
    if split is not None:
        events = [ev for ev in events if ev["split"] == split]
    if visibility is not None:
        events = [ev for ev in events if ev["visibility"] == visibility]
    return events


class _SplitAwareSuite(DenolleGroupSuite):
    """Mixin: filters events by ``split`` and ``visibility`` at items() time.

    All five STA/LTA suites accept the same two keyword args. Defaults to
    "no filter"; set the env var ``REPERE_STALTA_SPLIT`` for a process-wide default.
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
    dataset_id = "sta_lta"
    suite_id = "intent_extraction"
    version = "v0.1"

    def _compose(self, ev: dict) -> tuple[str, dict, dict, dict]:
        from datetime import timedelta

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
        scorer_spec = {
            "name": "json_extraction",
            "config": {
                "required_fields": list(gold),
                "field_tolerances": {"starttime": 5.0, "endtime": 5.0},
            },
        }
        meta = {
            "event_id": ev["id"],
            "category": ev["category"],
            "cutoff_date": ev["cutoff_date"],
            "expected_detection": ev["expected_detection"],
        }
        return prompt, gold, scorer_spec, meta

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for ev in self._events():
            prompt, gold, scorer_spec, _ = self._compose(ev)
            yield (prompt, gold, make_scorer_from_spec(scorer_spec))

    def export_rows(self) -> Iterable[BenchmarkRow]:
        for ev in self._events():
            prompt, gold, scorer_spec, meta = self._compose(ev)
            yield BenchmarkRow(
                id=f"{self.dataset_id}/{self.suite_id}/{ev['id']}",
                dataset_id=self.dataset_id,
                suite_id=self.suite_id,
                version=self.version,
                task_kind=self.task_kind.value,
                split=ev["split"],
                visibility=ev["visibility"],
                prompt=prompt,
                gold=gold,
                scorer_spec=scorer_spec,
                metadata=meta,
            )


class STALTAFetchCodeSuite(_SplitAwareSuite):
    """Structured request to ObsPy waveform-fetching code."""

    task_kind = TaskKind.CODE_GENERATION
    dataset_id = "sta_lta"
    suite_id = "fetch_code"
    version = "v0.1"

    def _compose(self, ev: dict) -> tuple[str, dict, dict, dict]:
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
        scorer_spec = {
            "name": "code_execution",
            "config": {
                "required_calls": ["Client", ".get_waveforms"],
                "expected_artifact_keys": ["n_traces", "sampling_rate"],
                "artifact_predicates": {
                    "n_traces": "int_ge_1",
                    "sampling_rate": "float_gt_0",
                },
                "timeout_s": 60.0,
            },
        }
        meta = {
            "event_id": ev["id"],
            "category": ev["category"],
            "cutoff_date": ev["cutoff_date"],
            "station": dict(station),
        }
        return prompt, gold, scorer_spec, meta

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for ev in self._events():
            prompt, gold, scorer_spec, _ = self._compose(ev)
            yield (prompt, gold, make_scorer_from_spec(scorer_spec))

    def export_rows(self) -> Iterable[BenchmarkRow]:
        for ev in self._events():
            prompt, gold, scorer_spec, meta = self._compose(ev)
            yield BenchmarkRow(
                id=f"{self.dataset_id}/{self.suite_id}/{ev['id']}",
                dataset_id=self.dataset_id,
                suite_id=self.suite_id,
                version=self.version,
                task_kind=self.task_kind.value,
                split=ev["split"],
                visibility=ev["visibility"],
                prompt=prompt,
                gold=gold,
                scorer_spec=scorer_spec,
                metadata=meta,
            )


class STALTATriggerCodeSuite(_SplitAwareSuite):
    """Loaded ObsPy stream to STA/LTA trigger code."""

    task_kind = TaskKind.CODE_GENERATION
    dataset_id = "sta_lta"
    suite_id = "trigger_code"
    version = "v0.1"

    def _compose(self, ev: dict) -> tuple[str, dict, dict, dict]:
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
        scorer_spec = {
            "name": "code_execution",
            "config": {
                "required_calls": ["classic_sta_lta", "trigger_onset"],
                "expected_artifact_keys": ["n_triggers"],
                "artifact_predicates": {
                    "n_triggers": "int_ge_1" if ev["expected_detection"] else "int_eq_0",
                },
                "timeout_s": 30.0,
            },
        }
        meta = {
            "event_id": ev["id"],
            "category": ev["category"],
            "cutoff_date": ev["cutoff_date"],
            "stalta_params": dict(p),
        }
        return prompt, gold, scorer_spec, meta

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for ev in self._events():
            prompt, gold, scorer_spec, _ = self._compose(ev)
            yield (prompt, gold, make_scorer_from_spec(scorer_spec))

    def export_rows(self) -> Iterable[BenchmarkRow]:
        for ev in self._events():
            prompt, gold, scorer_spec, meta = self._compose(ev)
            yield BenchmarkRow(
                id=f"{self.dataset_id}/{self.suite_id}/{ev['id']}",
                dataset_id=self.dataset_id,
                suite_id=self.suite_id,
                version=self.version,
                task_kind=self.task_kind.value,
                split=ev["split"],
                visibility=ev["visibility"],
                prompt=prompt,
                gold=gold,
                scorer_spec=scorer_spec,
                metadata=meta,
            )


class STALTAPlotSuite(_SplitAwareSuite):
    """Plot waveform and STA/LTA triggers against approved goldens."""

    task_kind = TaskKind.PLOTTING
    dataset_id = "sta_lta"
    suite_id = "plot"
    version = "v0.1"

    @staticmethod
    def _golden_dir() -> Path:
        return Path(
            os.environ.get("REPERE_STALTA_GOLDEN_DIR", Path(__file__).parent / "data" / "golden")
        )

    def _compose(self, ev: dict) -> tuple[str, dict, dict, dict]:
        station = ev["recommended_stations"][0]
        golden = self._golden_dir() / f"{ev['id']}.png"
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
        if golden.exists():
            scorer_spec = {
                "name": "plot_ssim",
                "config": {
                    "golden_png_path": str(golden),
                    "ssim_threshold": 0.85,
                    "timeout_s": 60.0,
                },
            }
        else:
            # Sentinel: scorer returns 0.0 until a golden PNG is approved.
            scorer_spec = {"name": "zero", "config": {"reason": "missing_golden"}}
        meta = {
            "event_id": ev["id"],
            "category": ev["category"],
            "cutoff_date": ev["cutoff_date"],
            "station": dict(station),
            "golden_exists": golden.exists(),
        }
        return prompt, gold, scorer_spec, meta

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for ev in self._events():
            prompt, gold, scorer_spec, _ = self._compose(ev)
            yield (prompt, gold, make_scorer_from_spec(scorer_spec))

    def export_rows(self) -> Iterable[BenchmarkRow]:
        for ev in self._events():
            prompt, gold, scorer_spec, meta = self._compose(ev)
            yield BenchmarkRow(
                id=f"{self.dataset_id}/{self.suite_id}/{ev['id']}",
                dataset_id=self.dataset_id,
                suite_id=self.suite_id,
                version=self.version,
                task_kind=self.task_kind.value,
                split=ev["split"],
                visibility=ev["visibility"],
                prompt=prompt,
                gold=gold,
                scorer_spec=scorer_spec,
                metadata=meta,
            )


class STALTAReportSuite(_SplitAwareSuite):
    """STA/LTA detection result to concise technical report."""

    task_kind = TaskKind.REPORT_DRAFTING
    dataset_id = "sta_lta"
    suite_id = "report"
    version = "v0.1"

    def _compose(self, ev: dict) -> tuple[str, dict, dict, dict]:
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
                config: dict[str, Any] = {
                    "expected_detection": True,
                    "origin_time_iso": ev["origin_time"],
                    "magnitude": ev.get("magnitude"),
                    "required_terms": ["blast"],
                    "forbidden_terms": ["tectonic earthquake", "earthquake of magnitude"],
                }
            else:
                config = {
                    "expected_detection": True,
                    "origin_time_iso": ev["origin_time"],
                    "origin_time_tolerance_s": 60.0,
                    "magnitude": ev.get("magnitude"),
                    "magnitude_tolerance": 0.7,
                }
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
            config = {
                "expected_detection": False,
                "required_terms": ["no events"],
                "forbidden_terms": ["detected an earthquake", "tectonic event"],
            }
        gold = {"event_id": ev["id"], "category": ev["category"]}
        scorer_spec = {"name": "report", "config": config}
        meta = {
            "event_id": ev["id"],
            "category": ev["category"],
            "cutoff_date": ev["cutoff_date"],
            "expected_detection": ev["expected_detection"],
        }
        return prompt, gold, scorer_spec, meta

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for ev in self._events():
            prompt, gold, scorer_spec, _ = self._compose(ev)
            yield (prompt, gold, make_scorer_from_spec(scorer_spec))

    def export_rows(self) -> Iterable[BenchmarkRow]:
        for ev in self._events():
            prompt, gold, scorer_spec, meta = self._compose(ev)
            yield BenchmarkRow(
                id=f"{self.dataset_id}/{self.suite_id}/{ev['id']}",
                dataset_id=self.dataset_id,
                suite_id=self.suite_id,
                version=self.version,
                task_kind=self.task_kind.value,
                split=ev["split"],
                visibility=ev["visibility"],
                prompt=prompt,
                gold=gold,
                scorer_spec=scorer_spec,
                metadata=meta,
            )


ALL_SUITES = [
    STALTAIntentExtractionSuite(),
    STALTAFetchCodeSuite(),
    STALTATriggerCodeSuite(),
    STALTAPlotSuite(),
    STALTAReportSuite(),
]
