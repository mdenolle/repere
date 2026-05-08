# Worked example: Nisqually 2001 (regional intraslab)

**Input**
- Station: UW.LON..BHZ
- Origin time: 2001-02-28T18:54:32.8 UTC
- Magnitude: M6.8 (deep intraslab, 51.7 km)

**Expected workflow output**

1. Fetch ±450 s around origin.
2. Bandpass 1–20 Hz, demean/detrend/taper.
3. STA=2.0 s, LTA=10.0 s, on=3.5, off=1.5.
4. Triggers ≥ 1; first trigger ≈ 1–2 s after origin (P-arrival distance ~70 km).
5. Catalog match: PNSN catalog ID `uw10262801`, M6.8, depth 51.7 km, 47.149°N
   122.727°W. Distance to UW.LON ≈ 60 km; expected P-arrival ≈ 10 s after
   origin time.
6. Report: "Detection consistent with PNSN catalog event uw10262801 (M6.8,
   depth 51.7 km). First STA/LTA trigger at <time>; consistent with the
   regional P-arrival travel time at this distance."

**What success looks like**
- Numerical match to catalog magnitude within ±0.5.
- Origin-time match within 60 s.
- Report names the station, the threshold used, and the magnitude.

**What failure looks like**
- Reporting "no event detected" (false negative on the easiest case).
- Reporting magnitude as M4.x (off by >0.5).
- Inventing a catalog ID that does not start with `uw`.
