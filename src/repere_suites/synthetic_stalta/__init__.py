"""Ridgecrest synthetic STA/LTA detection suite.

Synthetic detection cases derived from one real 2019 M7.1 Ridgecrest waveform
by deterministic + seeded transforms (`scripts/build_synthetic_stalta.py`).
Positives carry known onset(s); negatives are noise-only (correct answer `[]`).
Scored by `detection_picks` (pick_f1). The suite reads only `cases.yaml`, so it
needs neither obspy nor numpy nor a network.
"""

from __future__ import annotations

from . import items, scorers
from .items import ALL_SUITES, CASES_PATH, SyntheticSTALTASuite

__all__ = [
    "ALL_SUITES",
    "CASES_PATH",
    "SyntheticSTALTASuite",
    "items",
    "scorers",
]
