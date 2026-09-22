"""Canonical STA/LTA processing and plotting recipe.

The same recipe is used by `scripts/build_plot_goldens.py` to generate plot
goldens, by the seismic-plotting skill's reference docs, and by the test
suite to detect drift in the recipe itself. Pinning a single function as the
source of truth means a model that wants to match the goldens must produce
output equivalent to this code.

The recipe takes a stream and STA/LTA parameters and returns the processed
trace, the characteristic function, and the trigger onsets. The plotting
function takes those plus a station/event label and writes `plot.png` to a
directory of the caller's choosing.

This module imports ObsPy lazily (matplotlib is the hard dep). When ObsPy is
not available, callers can pass an already-processed numpy array via
`render_canonical_plot_arrays`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np


# -----------------------------------------------------------------------------
# Canonical STA/LTA parameters per source class
# -----------------------------------------------------------------------------

DEFAULT_STALTA = {
    "regional_earthquake": dict(filter_band=(1.0, 20.0), sta=2.0, lta=10.0, on=3.5, off=1.5),
    "teleseism": dict(filter_band=(0.02, 0.5), sta=5.0, lta=60.0, on=3.0, off=1.5),
    "noise_day": dict(filter_band=(1.0, 20.0), sta=2.0, lta=10.0, on=3.5, off=1.5),
    "quarry_blast": dict(filter_band=(1.0, 20.0), sta=0.5, lta=8.0, on=4.0, off=1.5),
    "volcanic_lp": dict(filter_band=(0.5, 5.0), sta=1.0, lta=12.0, on=3.5, off=1.5),
}


# -----------------------------------------------------------------------------
# Plotting recipe — pure numpy in/out so it can run with or without ObsPy
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class CanonicalPlotInput:
    times: np.ndarray  # seconds since trace start
    waveform: np.ndarray  # detrended/filtered counts
    cft: np.ndarray  # STA/LTA characteristic function, same shape as waveform
    trigger_indices: Iterable[int]
    station_label: str  # e.g. "UW.LON"
    event_label: str  # e.g. "M6.8 Nisqually deep intraslab earthquake"
    on_thresh: float
    no_events: bool = False


def render_canonical_plot(arr: CanonicalPlotInput, out_path: str | Path) -> Path:
    """Render the canonical two-panel plot exactly as `seismic-plotting`'s
    `matplotlib-recipes.md` describes, and save to `out_path`.

    Returns the absolute path of the written PNG.
    """
    import matplotlib

    matplotlib.use("Agg")  # safe for headless / sandbox use
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(10, 6))

    ax1.plot(arr.times, arr.waveform, color="black", linewidth=0.5)
    ax1.set_ylabel("Counts")
    title = f"{arr.station_label} — {arr.event_label}"
    if arr.no_events:
        title += "\nno events detected above threshold"
    ax1.set_title(title)

    ax2.plot(arr.times, arr.cft, color="navy", linewidth=0.7)
    ax2.axhline(arr.on_thresh, color="grey", linestyle=":", linewidth=0.5)
    ax2.set_xlabel("Time (s) since trace start")
    ax2.set_ylabel("STA/LTA")

    for idx in arr.trigger_indices:
        if 0 <= idx < len(arr.times):
            t_on = arr.times[idx]
            ax1.axvline(t_on, color="red", linestyle="--", linewidth=0.8)
            ax2.axvline(t_on, color="red", linestyle="--", linewidth=0.8)

    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return out_path.resolve()


# -----------------------------------------------------------------------------
# Real-data path: ObsPy stream → CanonicalPlotInput
# -----------------------------------------------------------------------------


def stream_to_canonical_input(
    stream: Any,
    *,
    event_label: str,
    sta_s: float,
    lta_s: float,
    on_thresh: float,
    off_thresh: float,
    filter_band: tuple[float, float],
) -> CanonicalPlotInput:
    """Run the canonical preprocessing + STA/LTA on an ObsPy Stream and
    return the inputs the plotting function expects."""
    from obspy.signal.trigger import classic_sta_lta, trigger_onset

    st = stream.copy()
    st.merge(method=1, fill_value=0)
    st.detrend("demean").detrend("linear").taper(0.05)
    st.filter("bandpass", freqmin=filter_band[0], freqmax=filter_band[1], corners=4, zerophase=True)
    tr = st[0]

    sr = tr.stats.sampling_rate
    sta_n = max(1, int(sta_s * sr))
    lta_n = max(sta_n + 1, int(lta_s * sr))

    cft = classic_sta_lta(tr.data, sta_n, lta_n)
    triggers = trigger_onset(cft, on_thresh, off_thresh)
    trigger_indices = [
        int(on) for on, _off in (triggers.tolist() if hasattr(triggers, "tolist") else triggers)
    ]

    station = tr.stats
    station_label = f"{station.network}.{station.station}"

    return CanonicalPlotInput(
        times=tr.times(),
        waveform=tr.data,
        cft=cft,
        trigger_indices=trigger_indices,
        station_label=station_label,
        event_label=event_label,
        on_thresh=float(on_thresh),
        no_events=len(trigger_indices) == 0,
    )


# -----------------------------------------------------------------------------
# Synthetic-data path: deterministic placeholder when network is unavailable
# -----------------------------------------------------------------------------


def synthetic_canonical_input(
    *,
    event_id: str,
    station_label: str,
    event_label: str,
    duration_s: float,
    sampling_rate_hz: float,
    sta_s: float,
    lta_s: float,
    on_thresh: float,
    off_thresh: float,
    has_event: bool,
    seed: int = 0,
) -> CanonicalPlotInput:
    """Deterministic stand-in for a real waveform.

    Used as a fallback when FDSN or ObsPy is unavailable. The output is *not*
    a research-grade golden — it's a structurally correct placeholder so the
    benchmark has something to compare against during local development.
    Files generated this way must be regenerated on a machine with ObsPy +
    FDSN access before any benchmark publication.
    """
    rng = np.random.default_rng(seed + abs(hash(event_id)) % (2**31))
    n = int(duration_s * sampling_rate_hz)
    t = np.arange(n) / sampling_rate_hz
    noise = rng.normal(0.0, 1.0, size=n)

    waveform = noise.astype(np.float64)
    if has_event:
        # A synthetic Ricker-like burst placed at ~40% of the window. The
        # amplitude is chosen so the boxcar STA/LTA below produces a clear
        # peak above on_thresh for typical (sta=2s, lta=10s, on=3.5) settings.
        burst_center = int(0.4 * n)
        burst_width = int(3.0 * sampling_rate_hz)
        burst_idx = np.arange(
            max(0, burst_center - burst_width), min(n, burst_center + burst_width)
        )
        burst_t = (burst_idx - burst_center) / sampling_rate_hz
        amp = (
            30.0 * (1 - 2 * (np.pi * 2.0 * burst_t) ** 2) * np.exp(-((np.pi * 2.0 * burst_t) ** 2))
        )
        waveform[burst_idx] += amp

    # Compute STA/LTA on the synthetic trace using a simple boxcar formulation
    sta_n = max(1, int(sta_s * sampling_rate_hz))
    lta_n = max(sta_n + 1, int(lta_s * sampling_rate_hz))
    sq = waveform**2
    # cumulative-sum trick for boxcar means
    csum = np.concatenate(([0.0], np.cumsum(sq)))
    sta = (csum[sta_n:] - csum[:-sta_n]) / sta_n
    lta = (csum[lta_n:] - csum[:-lta_n]) / lta_n
    # align lengths
    pad = lta_n - sta_n
    sta = sta[pad:]
    cft = np.zeros_like(waveform)
    valid_end = lta.shape[0]
    cft[lta_n - 1 : lta_n - 1 + valid_end] = sta[:valid_end] / np.where(
        lta[:valid_end] > 0, lta[:valid_end], 1.0
    )

    triggers: list[int] = []
    above = cft > on_thresh
    if has_event and above.any():
        first = int(np.argmax(above))
        triggers.append(first)

    return CanonicalPlotInput(
        times=t,
        waveform=waveform,
        cft=cft,
        trigger_indices=triggers,
        station_label=station_label,
        event_label=event_label,
        on_thresh=float(on_thresh),
        no_events=len(triggers) == 0,
    )


__all__ = [
    "CanonicalPlotInput",
    "DEFAULT_STALTA",
    "render_canonical_plot",
    "stream_to_canonical_input",
    "synthetic_canonical_input",
]
