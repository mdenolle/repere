"""T1 oracle: clock offset of OO.HYS14 from the chronfix correction files.

The reference is chronfix's delivered hourly ``delta_t`` series
(``examples/HYS14/{hour_times.npy, delta_t_hourly_clean.npy, trigger_periods.csv}``
at coszo-hub/chronfix commit 486f05b). What that series is, and is not, is
stated in DESIGN.md §3.1c: it is a software estimate from ambient-noise
cross-correlation against HYS12, validated closed-loop; the authors quote
sigma_total ~ 0.08 s typical, 0.17 s worst case, on a 0.125 s picker quantum.
It is the best reference available, but calling it "physics-verified" rests
on the HYS12 clock being good, which is asserted in the chronfix docs and not
demonstrated in the repo. See OPEN_QUESTIONS.md Q7.

Files are fetched by ``scripts/rca_fetch_external.py`` into
``data/external/chronfix/HYS14/`` (gitignored) and hash-checked there. This
module never downloads anything.

Sign convention (chronfix ``clock_model.py``): delta_t > 0 means the station
clock is late; a sample stamped ``t_apparent`` was recorded at
``t_apparent - delta_t``.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import HERE

DEFAULT_DIR = HERE / "data" / "external" / "chronfix" / "HYS14"


def _dir() -> Path:
    return Path(os.environ.get("REPERE_RCA_CHRONFIX_DIR", DEFAULT_DIR))


def _load(directory: Path | None = None):
    import numpy as np

    d = directory or _dir()
    ht = d / "hour_times.npy"
    dt = d / "delta_t_hourly_clean.npy"
    if not ht.is_file() or not dt.is_file():
        raise FileNotFoundError(
            f"chronfix HYS14 files not found under {d}; run scripts/rca_fetch_external.py"
        )
    hours = np.load(ht)  # datetime64[h]
    delta = np.load(dt)  # float64 seconds, NaN inside triggers
    return hours, delta


def chronfix_offset(*, at_utc: str, directory: str | None = None, **_: Any) -> dict[str, Any]:
    """Return ``{"clock_offset_s": float | None, "in_trigger": bool}`` at an hour.

    ``at_utc`` is ISO-8601; it is floored to the hour. ``None`` means chronfix
    has no value there (inside a resync trigger interval or off the axis),
    which the scorer treats as "no reference, void", not as zero.
    """
    import numpy as np

    hours, delta = _load(Path(directory) if directory else None)
    t = datetime.fromisoformat(at_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    key = np.datetime64(t.replace(minute=0, second=0, microsecond=0, tzinfo=None), "h")
    idx = np.searchsorted(hours, key)
    if idx >= len(hours) or hours[idx] != key:
        return {"clock_offset_s": None, "in_trigger": False, "reason": "hour not on chronfix axis"}
    val = float(delta[idx])
    if np.isnan(val):
        return {"clock_offset_s": None, "in_trigger": True, "reason": "inside a resync trigger"}
    return {"clock_offset_s": val, "in_trigger": False}


def chronfix_triggers(*, directory: str | None = None, **_: Any) -> dict[str, Any]:
    """Return the 32 resync intervals as UTC ISO strings (from trigger_periods.csv)."""
    import numpy as np

    d = Path(directory) if directory else _dir()
    hours, _ = _load(d)
    rows = []
    with open(d / "trigger_periods.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            i0, i1 = int(r["start_index"]), int(r["end_index"])
            rows.append(
                {
                    "start_utc": str(np.datetime_as_string(hours[i0], unit="h")),
                    "end_utc": str(np.datetime_as_string(hours[min(i1, len(hours) - 1)], unit="h")),
                }
            )
    return {"triggers": rows, "n_triggers": len(rows)}


__all__ = ["chronfix_offset", "chronfix_triggers", "DEFAULT_DIR"]
