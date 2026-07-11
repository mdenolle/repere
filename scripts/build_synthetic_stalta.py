"""Build the Ridgecrest synthetic STA/LTA truth set.

A "very simple ObsPy query for a large regional earthquake signal, then a bunch
of stochastic/deterministic transformations to create synthetic cases"
(2019-07-06 M7.1 Ridgecrest mainshock, CI network).

Pipeline
--------
1. Fetch ONE real vertical broadband trace of the mainshock from FDSN (SCEDC,
   then IRIS/EarthScope as fallback), trying a short list of regional stations.
2. Preprocess (detrend, taper, 1-10 Hz bandpass) and resample to 10 Hz.
3. Cache the trimmed real seed as miniSEED in the repo (reproducibility: the
   fetch happens once; everything downstream is deterministic).
4. Define the reference onset by running classic STA/LTA on the clean seed.
5. Apply deterministic + *seeded* stochastic transforms to synthesise labelled
   detection cases — positives (event present, known onset[s]) and negatives
   (noise only, no onset). Negatives are first-class: an over-eager detector
   must return [] for them.
6. Write `cases.yaml` (the truth set: per-case waveform + gold onsets + params).

Run in the full pixi env (needs obspy + numpy):

    pixi run -e full python scripts/build_synthetic_stalta.py
    pixi run -e full python scripts/build_synthetic_stalta.py --offline  # synth seed

The suite and its tests only read `cases.yaml` (plain lists), so they need
neither obspy nor numpy nor a network.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parent.parent
SUITE_DIR = REPO / "src" / "frugalmind_suites" / "synthetic_stalta"
DATA_DIR = SUITE_DIR / "data"
SEED_MSEED = DATA_DIR / "ridgecrest_seed.mseed"
CASES_YAML = SUITE_DIR / "cases.yaml"

# Ridgecrest M7.1 mainshock.
ORIGIN = "2019-07-06T03:19:53"
SR = 10.0  # target sampling rate (Hz) — keeps the embedded arrays compact
WINDOW_S = 100.0  # seconds of signal per case
BAND = (1.0, 10.0)
# STA/LTA detector the tasks ask models to reproduce.
STA_S, LTA_S, THR_ON, THR_OFF = 1.0, 10.0, 3.5, 1.5

# Regional CI broadband candidates (~150-350 km; unlikely to be clipped).
STATIONS = [
    ("CI", "PASC", "--", "BHZ"),
    ("CI", "MWC", "--", "BHZ"),
    ("CI", "SBC", "--", "BHZ"),
    ("CI", "PLM", "--", "BHZ"),
    ("CI", "RIO", "--", "BHZ"),
]


def _fetch_seed() -> tuple[np.ndarray, dict]:
    """Fetch and preprocess one real Ridgecrest trace; return (data, meta)."""
    from obspy import UTCDateTime
    from obspy.clients.fdsn import Client

    t0 = UTCDateTime(ORIGIN)
    for client_name in ("SCEDC", "IRIS"):
        try:
            client = Client(client_name, timeout=30)
        except Exception:
            continue
        for net, sta, loc, cha in STATIONS:
            try:
                st = client.get_waveforms(
                    net, sta, "" if loc == "--" else loc, cha,
                    t0, t0 + WINDOW_S + 60,
                )
            except Exception:
                continue
            if not st:
                continue
            st.merge(fill_value="interpolate")
            st.detrend("demean")
            st.detrend("linear")
            st.taper(0.05)
            st.filter("bandpass", freqmin=BAND[0], freqmax=BAND[1], corners=4)
            st.resample(SR)
            tr = st[0].trim(t0, t0 + WINDOW_S)
            meta = {
                "source": f"FDSN {client_name} {net}.{sta}.{cha}",
                "origin": ORIGIN,
                "sampling_rate": SR,
            }
            print(f"fetched {net}.{sta}.{cha} from {client_name}: {tr.stats.npts} samples")
            st.write(str(SEED_MSEED), format="MSEED")
            return tr.data.astype(float), meta
    raise RuntimeError("no station returned data; try --offline")


def _synthetic_seed() -> tuple[np.ndarray, dict]:
    """Deterministic analytic surrogate: a filtered wavelet on a quiet baseline."""
    n = int(WINDOW_S * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(0)
    x = 0.02 * rng.standard_normal(n)  # ambient noise floor
    onset = 30.0
    env = np.exp(-(t - onset) / 8.0)
    env[t < onset] = 0.0
    x += env * np.sin(2 * np.pi * 3.0 * (t - onset))  # damped 3 Hz arrival
    return x, {"source": "analytic-synthetic", "origin": ORIGIN, "sampling_rate": SR}


def _reference_onset(data: np.ndarray) -> float:
    """First STA/LTA trigger onset (seconds) on the clean seed."""
    from obspy.signal.trigger import classic_sta_lta, trigger_onset

    cft = classic_sta_lta(data, int(STA_S * SR), int(LTA_S * SR))
    trigs = trigger_onset(cft, THR_ON, THR_OFF)
    if len(trigs) == 0:
        raise RuntimeError("no trigger on clean seed; check preprocessing/params")
    return float(trigs[0][0]) / SR


def _round(x: np.ndarray) -> list[float]:
    return [round(float(v), 4) for v in x]


def _build_cases(seed: np.ndarray, t0: float) -> list[dict]:
    """Deterministic + seeded transforms -> labelled detection cases."""
    n = len(seed)
    noise_seg = seed[: int(t0 * SR) - 5]  # pre-event window (real noise)
    if len(noise_seg) < 20:
        noise_seg = 0.01 * np.random.default_rng(7).standard_normal(n)
    amp = float(np.max(np.abs(seed)))

    def tiled_noise(rng_seed: int) -> np.ndarray:
        rng = np.random.default_rng(rng_seed)
        return 0.15 * amp * rng.standard_normal(n)

    cases: list[dict] = []

    # --- positives -------------------------------------------------------
    cases.append({"id": "p1-baseline", "transform": "real signal, unmodified",
                  "data": seed.copy(), "onsets_s": [round(t0, 2)]})

    cases.append({"id": "p2-low-amplitude", "transform": "amplitude x0.25 (low SNR)",
                  "data": 0.25 * seed, "onsets_s": [round(t0, 2)]})

    cases.append({"id": "p3-additive-noise", "transform": "additive Gaussian noise, seed=1",
                  "data": seed + tiled_noise(1), "onsets_s": [round(t0, 2)]})

    shift = 20.0
    shifted = np.concatenate([tiled_noise(2)[: int(shift * SR)], seed])[:n]
    cases.append({"id": "p4-time-shift", "transform": f"onset delayed +{shift:g}s",
                  "data": shifted, "onsets_s": [round(t0 + shift, 2)]})

    gap = 55.0
    second = np.concatenate([np.zeros(int(gap * SR)), 0.6 * seed])[:n]
    two = seed.copy()
    two[: len(second)] += second[: len(two)]
    cases.append({"id": "p5-two-events", "transform": f"second (0.6x) event at +{gap:g}s",
                  "data": two, "onsets_s": [round(t0, 2), round(t0 + gap, 2)]})

    # --- negatives (expected: no detection) ------------------------------
    cases.append({"id": "n1-gaussian-noise", "transform": "Gaussian noise only, seed=3",
                  "data": tiled_noise(3), "onsets_s": []})

    real_noise = np.resize(noise_seg, n)
    cases.append({"id": "n2-real-preevent-noise", "transform": "tiled real pre-event noise",
                  "data": real_noise, "onsets_s": []})

    out = []
    for c in cases:
        d = c["data"]
        out.append({
            "id": c["id"],
            "transform": c["transform"],
            "expected_detection": len(c["onsets_s"]) > 0,
            "onsets_s": c["onsets_s"],
            "sampling_rate": SR,
            "npts": int(len(d)),
            "sta_s": STA_S, "lta_s": LTA_S, "thr_on": THR_ON, "thr_off": THR_OFF,
            "onset_tolerance_s": 1.5,
            "split": "validation",
            "visibility": "public",
            "waveform": _round(d),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true",
                    help="use a deterministic analytic seed instead of FDSN")
    args = ap.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    seed, meta = _synthetic_seed() if args.offline else _fetch_seed()
    t0 = _reference_onset(seed)
    print(f"reference onset: {t0:.2f}s")
    cases = _build_cases(seed, t0)

    doc = {
        "meta": {**meta, "band_hz": list(BAND), "detector": {
            "sta_s": STA_S, "lta_s": LTA_S, "thr_on": THR_ON, "thr_off": THR_OFF}},
        "cases": cases,
    }
    CASES_YAML.write_text(yaml.safe_dump(doc, sort_keys=False, width=100))
    n_pos = sum(1 for c in cases if c["expected_detection"])
    print(f"wrote {CASES_YAML} : {len(cases)} cases ({n_pos} positive, "
          f"{len(cases) - n_pos} negative)")
    print(json.dumps({c["id"]: c["onsets_s"] for c in cases}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
