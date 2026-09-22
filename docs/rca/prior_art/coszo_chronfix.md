# coszo-hub public repositories: what the code and data actually contain

Scope: five public repos of GitHub org `coszo-hub`, cloned depth 1 on 2026-09-14, plus https://coszo.org fetched the same day with curl. Every statement below points at a file and line in the clones. Anything I could not point at is marked NOT VERIFIED.

Clone root (absolute): `<scratch>/coszo/`. File references below are relative to `<root>/<repo>/`.

## 0. Repositories and HEAD commits

| repo | HEAD | commit date | committer | clone size |
|---|---|---|---|---|
| chronfix | 486f05bcdaad26a1855ee90c987c41b7d36b835a | 2026-07-28T11:34:27-07:00 | Maleen Kidiwela | 3.1 MB |
| coszo-hub.github.io | 3ddee1013508f875371b7a666a89af539a70a741 | 2026-09-06T23:03:49Z | github-actions[bot] | 148 files |
| sea-water-velocity | 5be90a0d2c92c4f7e4fdf06ceae98f66d22a6b25 | 2026-09-02T09:13:31-07:00 | Maleen Kidiwela | 335 MB |
| absolute-seafloor-pressure | 43a420c7bf143007b5fa45963fc2c0dc1681cf75 | 2026-08-03T18:19:09-07:00 | Maleen Kidiwela | 5.4 MB |
| dive-index-hindcast | 85e5318548fd2f3c0447f7d254e166c869a6b60d | 2026-09-07T17:48:53-07:00 | William Wilcock | 21 MB |

The GitHub API (`/orgs/coszo-hub/repos`, queried 2026-09-14) lists exactly these five public repos. There is no public `chronos` repo in the org. Depth-1 clones show one commit each; chronfix's visible commit message is "Add MIT License to the project".

## 1. What coszo.org says

Fetched with curl, HTTP 200, 75,752 bytes; the repo's `coszo-hub.github.io/index.html` has the same byte count (not diffed, NOT VERIFIED identical).

What COSZO is (homepage text): "The Cascadia Offshore Subduction Zone Observatory (COSZO) is a National Science Foundation funded Mid-scale Research Infrastructure (RI-1) implementation project. Scientists and engineers from the University of Washington School of Oceanography, Department of Earth and Space Sciences, and Applied Physics Laboratory, together with the Scripps Institution of Oceanography, are adding geophysical instrumentation to the Ocean Observatories Initiative Regional Cabled Array off the coast of Oregon." Stated purpose: continuous seafloor data to study how the Cascadia fault works and to support offshore earthquake and tsunami early warning. The RCA is described as established in 2015.

Who runs it (`coszo-hub.github.io/data/people.csv`, 37 rows):

| role | name | affiliation | line |
|---|---|---|---|
| Principal Investigator | William Wilcock | UW School of Oceanography | 2 |
| Chief Engineer | Mike Harrington | UW APL | 3 |
| Co-PI | David Schmidt, Deborah Kelley, Harold Tobin | UW ESS / Oceanography / ESS | 4-6 |
| Science, Training, and Outreach Team | Marine Denolle | UW ESS | 7 |
| Project Manager | Mika Thompson | UW ESS | 8 |
| Postdoctoral Scholar | Maleen Kidiwela | UW Oceanography | 28 |
| Scripps group | Mark Zumberge, Glenn Sasagawa, Joel White, Matthew Cook | UCSD SIO | 31-34 |
| Science Advisory Committee | Anne Sheehan (chair), Matt Wei, Helen Janiszewski, Valerie Sahakian | CU Boulder, URI, U Hawaii, U Oregon | 35-38 |

Sensors and data (site navigation and `data/data_channels.csv`, 53 rows): Broadband Seismometer & Strong Motion, Differential Pressure Gauge, Hydrophone, Absolute Pressure Gauge, "GSSM" (Calibrated Pressure & Acceleration), "CSCPR" (Calibrated Pressure), Current Meter. The CSV lists four COSZO stations, `CZMID` (Mid Slope), `CZOFF` (Oregon Offshore), `CZOSH` (Outer Shelf), `CZSHF` (Oregon Shelf), with SEED channel codes and rates, e.g. broadband HHZ 200 Hz / BHZ 40 Hz / MHZ 8 Hz / LHZ 1 Hz (lines 2-9), hydrophone JDH 10 kHz (line 14), GSSM at loc 30/31 (18-35), CSCPR loc 40/41 (36-39), current meter loc 20 (40-54). The GSSM and CSCPR acronyms are not expanded anywhere in the CSV (NOT VERIFIED what they stand for). The only mention of HYS14 on the site is the absolute-pressure page: `OO.HYS14` loc `10`, channels UDO/UK1 with links to ds.iris.edu MDA (`build_pages.py:1815-1816`). HYS12 does not appear on the site.

## 2. chronfix

Absolute path: `<root>/chronfix/`. Tracked files (`git ls-files`, 21 entries): `README.md`, `LICENSE`, `pyproject.toml`, `.gitignore`, `.DS_Store` (tracked despite `.gitignore`), `src/chronfix/{__init__,clock_model,correct}.py`, `src/chronfix/scripts/{__init__,apply_correction}.py`, `examples/HYS14 — Correction Method.md` (23,654 bytes, filename contains a literal em dash), `examples/HYS14/{README.md, delta_t_hourly.csv, delta_t_hourly_clean.npy, hour_times.npy, trigger_periods.csv, filter_and_triggers.png}`, `examples/HYS14/figures/{before_after_ccf, correction_function, peak_lag_after, peak_lag_before}.png`.

Absent: any `tests/` directory (README.md:141 lists one in the layout; none is tracked), notebooks, docs directory, CI, CITATION file, requirements file, MiniSEED data.

Below, "CM" means `examples/HYS14 — Correction Method.md`.

### 2a. What it does, step by step

**Verdict.** chronfix is only the *apply* step. It reads a three-file "correction directory" produced by a separate package called chronos, and rewrites MiniSEED timestamps. chronos is software, not hardware: README.md:5-7 says "chronos measures the clock error Δt(t) of one station against a reference station and writes a correction file", and CM:29-31 says chronos measures Δt "from cross-correlations against a reference station with known good timing (HYS12)". No chronos code is in this repo or anywhere public in the org.

**Inputs.**

1. Correction directory (README.md:103-109; `clock_model.py:62-91`):

| file | dtype, shape | meaning | loaded at |
|---|---|---|---|
| `delta_t_hourly_clean.npy` | float64, (31563,) | Δt in seconds per hour; NaN where masked | clock_model.py:72 |
| `hour_times.npy` | datetime64[h], (31563,) | hour axis aligned with Δt | clock_model.py:71 |
| `trigger_periods.csv` | CSV; only `start_index`, `end_index` are used | resync intervals, as indices into `hour_times` | clock_model.py:74-83 |

Sign convention: Δt > 0 means the station clock is late; a sample stamped `t_apparent` was recorded at `t_apparent − Δt(t_apparent)` (clock_model.py:10-12; `examples/HYS14/README.md:8`; CM:280-283).

2. Raw MiniSEED, one file per day at `<input-root>/<sta>/<yr>/<doy>/<sta>.<net>.<yr>.<doy>.<cha>` (`apply_correction.py:41-44`), read with `obspy.read` (line 63). No location code appears in the file pattern or CLI (lines 101-118).

**Where the corrections come from (documented in CM, code not present).** The chain is CM:13-25: `scripts/download_hys.py` → `diagnostics/hys_ccf.py` → `diagnostics/peak_lag_hourly.py` → `diagnostics/combine_clock_hourly.py` → `chronfix/scripts/filter_and_triggers.py` → `clock_model.py` → `correct.py` → `chronfix/scripts/correct_hys14.py`. Of these, only `clock_model.py` and `correct.py` are in the repo; `apply_correction.py` is the shipped driver (the doc names `correct_hys14.py`, CM:304 and 473, which is not tracked). README.md:111 attributes `filter_and_triggers` to `chronos.scripts`, CM:134 to `chronfix/scripts`; neither is present.

The documented measurement recipe, with its parameters:

| stage | parameters | CM lines |
|---|---|---|
| data | daily MHZ (8 Hz vertical) MiniSEED for `OO.HYS{12,14,B1}` from EarthScope FDSN, 2022-01-01 to present, plus StationXML `OO.{sta}..MHZ.xml` | 40-47 |
| per-day preprocessing | merge with zero fill, 100 s cosine taper at gaps, demean, detrend, high-pass 0.4 Hz, response removal to velocity, resample to 8 Hz, trim/pad to the UTC day | 60-69 |
| cross-correlation | ZZ, 30-min windows, 7.5-min step, raised-cosine phase whitening 0.5-3.8 Hz, one-bit normalisation, `irfft(conj(FFT(a))·FFT(b))`, lags ±60 s, per-day median stack | 71-77 |
| hourly peak lag | median of ~8 windows per UTC hour; lag of the global maximum of the Hilbert envelope of CC² | 94-98 |
| Δt from lag | anchor lag = late-window median (≈ 0 s); shift = anchor − peak_lag; Δt_HYS14 = −shift | 112-117 |
| cross-check | HYS14-HYSB1 pair, 0.1-0.3 Hz, reported as residual only | 118-120 |
| outlier filter | Hampel passes: 168 h/σ4.5/min 0.75 s; 72 h/4.0/0.60 s; 25 h/3.5/0.50 s; then 3-point continuity check at 3 s; then 240 h/σ6.5/min 1.30 s | 144-163 |
| trigger detection | consecutive retained-sample difference with abs value > 1.0 s flags `[t(k−1), t(k)]`; touching intervals merged | 177-184 |
| segment model | Theil-Sen slope < 0.05 s/day → segment replaced by its nanmedian; else centered 24 h rolling median then 6 h moving average; segments with < 5 finite samples left NaN; triggers left NaN | 196-211 |
| uncertainty | σ_lag ≈ 2 ms median / 5 ms p90; σ_model ≈ 0.077 s / 0.108 s; σ_total ≈ 0.08 s typical, 0.11 s p90, 0.17 s worst; quantum 0.125 s, floor 0.125/√12 ≈ 0.036 s | README.md:150-164 |

**Algorithm applied to MiniSEED (`src/chronfix/correct.py`).**

1. `correct_trace` (lines 28-81): get stable intervals overlapping the trace's apparent time span (`model.stable_intervals`, line 53; defined at clock_model.py:137-167 as the ranges between trigger intervals), slice the trace to each overlap (line 65), apply one of two methods (71-76), return a list of sub-traces. Empty list when Δt is unavailable.
2. `method="resample"` (default; `_resample`, lines 108-194): evaluate Δt at the chunk's apparent start and end (124-125); if either is NaN the chunk is dropped (126-127); `utc_start = apparent_start − Δt_start`, `utc_end = apparent_end − Δt_end` (128-129); build a regular output grid at the same nominal `fs` with `n_out = floor((utc_end − utc_start)·fs) + 1` (134-137); evaluate Δt at every output UTC sample (141-143); apparent target time of each output sample = `t_utc + Δt(t_utc)` (158); read the input via `np.interp` on the apparent grid (162, 179-180), i.e. linear resampling of the waveform; trim at the first NaN (144-155, 183-188); cast back to the input dtype (190); set `starttime = utc_start` (192). Note the docstring's "t_apparent ≈ t_utc + Δt(t_utc)" (line 112): Δt is evaluated at the UTC time, while the model convention defines it on apparent time. This is an approximation in the code; my estimate of its size is Δt'·Δt ≈ 1e-5 s/s × 50 s ≈ 5e-4 s at the worst drift (NOT VERIFIED by the authors).
3. `method="shift_only"` (`_shift_only`, 98-105): subtract Δt at the chunk start from `starttime`; data untouched. README.md:124-125 calls it lossless but valid only when within-segment drift is negligible.
4. Drift model: piecewise-linear between the hourly (already smoothed) samples, `np.interp` on epoch seconds (clock_model.py:113-125). Inside trigger intervals Δt is forced to NaN (128-133), so no output is produced there and the output is split at every trigger (README.md:8-9, 227-238). A decreasing Δt at a trigger leaves a UTC gap in the output; an increasing Δt leaves an overlap (README.md:231-234). Nothing else is done at resyncs.
5. Hour axis is not gap-free (see 2b). `np.interp` bridges an axis gap linearly unless a trigger covers it (clock_model.py:125, 128-133).

**Outputs (`src/chronfix/scripts/apply_correction.py`).** One MiniSEED per input day at `<output-root>/<sta>/<yr>/<doy>/<sta>.<net>.<yr>.<doy>.<cha>`, all sub-traces written into one file (74-78); `manifest.csv` appended with columns `date,input,output,segment,utc_start,utc_end,n_samples,method` (79-88, 153-164); log tallies ok/missing/no_overlap/err/chunks (166-168). CLI defaults: `--start 2022-01-01`, `--end today`, `--method resample`, `--workers 1` (112-115). Console entry point `chronfix-apply` (pyproject.toml:16). Each worker reloads the `ClockModel` from disk per day (line 68). `ClockModel.from_chronos` defaults to the server path `/home/seismic/chronos/data/clock_estimate/HYS14` and station `"HYS14"` (clock_model.py:22, 53, 68).

### 2b. The worked example: HYS14

| quantity | value | where |
|---|---|---|
| network | `OO` | README.md:35; examples/HYS14/README.md:3 |
| station corrected | `HYS14` | README.md:35; clock_model.py:53 |
| reference station | `HYS12` | README.md:77; CM:31 |
| cross-check station | `HYSB1` | CM:118-119, 127 |
| location code | none in code; StationXML path `OO.{sta}..MHZ.xml` implies blank | apply_correction.py:41-44; CM:47 |
| channel | `MHZ` | README.md:35; CM:40, 508 |
| analysis rate / picker quantum | 8 Hz / 0.125 s | README.md:160, 217; CM:189 |
| stated span | 2022-08 to 2026-05 | README.md:56; examples/HYS14/README.md:4 |
| data span | 2022-08-10T00 to 2026-05-01T22 | `hour_times.npy` first/last (computed) |
| CLI example start | 2022-08-13 | README.md:38 |
| input days / corrected days / segments | 1582 / 951 / 1059 | CM:315-319 |
| resyncs | 32 | README.md:56; examples/HYS14/README.md:10; CM:184, 533; `trigger_periods.csv` has 32 data rows (lines 2-33) |
| "visible resync resets" in the peak-lag plot | 23 | CM:342 |
| drift extremes, stated | ±50 s | README.md:71, 94, 166 |
| drift extremes, data | +49.859375 s at 2022-10-24T17; −49.734375 s at 2023-05-29T23 | computed from npy |
| longest curved segment, stated | 126 days, 56.7 s of drift | README.md:167-168, 210-211; CM:215, 398 |
| same segment, data | 2023-01-24T02 to 2023-05-29T23, 125.9 d, Δt from +7.000 to −49.734 s = 56.73 s | computed |
| last nonzero Δt | 3.875 s at 2025-05-08T20; zero thereafter through 2026-05-01 (356.7 d) | computed; README.md:71-72 |
| outliers masked, stated | 673 of 31,169 valid hours (2.2 %), 30,496 retained | CM:165-166 |
| finite values in delivered file | 30,791 of 31,563 (772 NaN) | computed; discrepancy with 30,496 not explained in repo, NOT VERIFIED |
| hour axis coverage | 31,563 entries over a 32,663 h span; 1,100 hours absent from the axis in 37 gaps; largest 441 h (2023-11-26T14 to 2023-12-15T00) | computed |
| NaN placement | all 752 hours inside trigger rows are NaN; 20 NaN hours lie outside triggers | computed |
| value quantization | 99.7 % of finite values are multiples of 1/480 s; 10.6 % are multiples of 1/8 s | computed; interpretation as the 0.125 s quantum passed through the smoother is NOT VERIFIED |
| reference CC RMS before/after | 12.8 → 40.6 (≈ 3.2×); pre-fix run 33.1 / 2.6× | README.md:92-93; CM:339, 402-405; figure text 12.82 / 40.55 |
| hourly outlier rates, uncorrected | n 31,563; >5 s 34.76 %; >20 s 12.76 %; >40 s 3.55 %; median 1.875 s | CM:388-390 |
| hourly outlier rates, deployed | n 30,084; 0.30 %; 0.20 %; 0.10 %; median 0.125 s | CM:393 |
| per-segment residual | median ≈ 0.000 s, MAD ≤ 0.115 s | README.md:208-210; CM:213-216 |
| trigger time resolution | ~1 hour | CM:501-504 |
| runtime | CCF ~40 min per run, correction ~5 min with 8 workers, ~1.5 h total | CM:481-487 |
| recovered hours from boundary-snap fix | ~7,800 | CM:381-384 |

**Does the repo contain the actual correction table?** Yes, in three forms in `examples/HYS14/`:

`trigger_periods.csv` (2,180 bytes, 32 data rows), first 5 rows verbatim (lines 1-6):

```
start_day,end_day,duration_days,start_index,end_index,max_abs_jump_in_period,num_triggered_steps_merged
8.333333333333334,9.083333333333334,0.75,200,218,1.125,1
73.83333333333333,88.25,14.416666666666671,1772,2118,32.875,2
89.125,90.91666666666667,1.7916666666666714,2139,2182,1.625,2
96.125,96.83333333333333,0.7083333333333286,2307,2324,2.25,1
109.91666666666667,110.0,0.0833333333333286,2638,2640,1.75,1
```

`start_day` equals `start_index/24` exactly (max difference 4.5e-13, computed), i.e. index-days, not calendar days. Mapped through `hour_times`, the first five triggers are 2022-08-20T00 to 08-21T00, 2022-10-24T18 to 11-08T04, 2022-11-09T01 to 11-10T20, 2022-11-16T01 to 11-16T18, 2022-11-29T20 to 12-02T00.

`delta_t_hourly.csv` (962,320 bytes, 31,563 data rows), first 5 rows verbatim (lines 1-6):

```
time_utc,delta_t_s
2022-08-10T00:00:00,0.10416666666666667
2022-08-10T01:00:00,0.10416666666666667
2022-08-10T02:00:00,0.10416666666666667
2022-08-10T03:00:00,0.10416666666666667
2022-08-10T04:00:00,0.10416666666666667
```

This CSV is not listed in the README's format table (README.md:105-109) and is not read by the code; it is bit-identical to `delta_t_hourly_clean.npy` (same times, same 772 NaNs, max abs difference 7e-17, computed). It is therefore the cleaned and segment-modeled series, not the raw hourly picks.

`delta_t_hourly_clean.npy` and `hour_times.npy` (252,632 bytes each): first five entries (index, hour, Δt) are 0 2022-08-10T00 0.10416667, 1 T01 0.10416667, 2 T02 0.10416667, 3 T03 0.10416667, 4 T04 0.10416667; last five (31558-31562, 2026-05-01T18 to T22) are all 0.0.

**MiniSEED data:** none in the repo. Figures: `figures/before_after_ccf.png` 1,168,082 B (1690×910), `figures/correction_function.png` 77,885 B (1820×560), `figures/peak_lag_before.png` 82,709 B (1540×630), `figures/peak_lag_after.png` 62,262 B (1540×630), `filter_and_triggers.png` 200,232 B (3054×1732).

### 2c. The validation

**Code: not in the repo.** The validation is described at CM:323-350 and CM:452-479: rerun `diagnostics/hys_ccf.py --pairs HYS12-HYS14 --tag corrected --input-root-override HYS14=<corrected root>` then `diagnostics/peak_lag_hourly.py --pair HYS12-HYS14_corrected` (CM:329-331, 476-478). Neither script is tracked.

**Parameters (as documented, same recipe as the measurement).** Reference station HYS12, channel MHZ, ZZ component, 8 Hz; high-pass 0.4 Hz then phase whitening 0.5-3.8 Hz; 30-min windows, 7.5-min step; hourly bins of ~8 windows; lags ±60 s; peak = global max of Hilbert envelope of CC² (CM:56-77, 94-98). The band where the ballistic peak lives is stated as 1-3 Hz (CM:370). Windows are per UTC hour; no other window length appears.

**Stated result.** Corrected hourly peak-lag track "flat at 0 across all 4 years"; reference RMS 12.8 → 40.6; daily 2D stack collapses to a vertical stripe at lag 0 (CM:337-342; README.md:76-99). Outlier-rate table CM:388-393 (reproduced in 2b). The doc records two earlier failures: an interpretation error corrected on 2026-05-04 (CM:352-385) and a loader bug that dropped trace starttimes and silently cancelled the correction (CM:412-448), fixed by trimming every trace to the canonical UTC day (CM:436-439).

**Figures.** `peak_lag_before.png`: title "HYS12-HYS14 hourly ballistic peak lag (global)", y axis "Peak lag (s)" ±60, x axis 2022-08-10 to 2026-05-01, one dot per hour; drift ramps to about +60 s (late 2022) and −50 s (mid 2023), then flat at 0 after mid-2025. `peak_lag_after.png`: same axes, title "HYS12-HYS14_corrected …", dots at 0 with sparse scatter at ±40-60 s. `before_after_ccf.png`: title "HYS12-HYS14 cross-correlations: before vs after chronfix (v3)", top row reference stacks with "RMS=12.82" and "RMS=40.55", bottom row daily CCF images, lags ±60 s, dates 2022-09 to 2026-05. `correction_function.png`: "HYS14 correction function (v3 segment-modeled hourly Δt)" with pink trigger bands. `filter_and_triggers.png`: two panels, "Filtered HYS12-HYS14 dt" and "Difference between consecutive retained filtered points", x axis "Elapsed time (days)" 0-1300.

**Is there a table of measured lags usable as independent ground truth?** No. The only numeric series shipped is the cleaned, segment-modeled Δt (npy and CSV above). The raw hourly peak-lag arrays, the Hampel-filtered series `delta_t_hourly_filtered_raw.npy`, the outlier mask, and the CCF arrays (`cc_daily.npy`, `cc_ref.npy`, `lags.npy`) are named at CM:79-88, 122-128, 167, 222-224, 528-531 but are not in the repo. The "before" figure is the only record of the raw picks, as an image. Further, the validation is closed-loop: the same station pair, method and band are used to measure and to check, so the repo contains no timing reference independent of the HYS12-HYS14 cross-correlation. HYS12's own timing is asserted "known good" (CM:30-31) with no supporting evidence in the repo.

### 2d. Dependencies, Python, license, authorship, citation

| item | value | where |
|---|---|---|
| dependencies | `numpy>=1.21`, `pandas>=1.3`, `obspy>=1.5` | pyproject.toml:11-15 |
| Python | `>=3.10` | pyproject.toml:9 |
| build | setuptools>=68, wheel; packages under `src/` | pyproject.toml:1-3, 18-20 |
| version | 0.1.0 | pyproject.toml:7; `__init__.py:16` |
| license | MIT, "Copyright (c) 2026 COSZO: Cascadia Subduction Zone Observatory" | pyproject.toml:10; LICENSE:1-3 |
| author | Maleen Kidiwela, seismic@uw.edu | pyproject.toml:9 |
| citation file | none (no CITATION.cff, no DOI, no paper reference) | `git ls-files` |
| documented runtime env for the full pipeline | conda env `noisepy2`, obspy ≥ 1.5, host "cascadia" | CM:454, 481 |
| stdlib used by the driver | argparse, csv, logging, concurrent.futures, datetime, pathlib | apply_correction.py:25-31 |

Hard-coded server paths appear in defaults and docs: `/home/seismic/chronos/data/clock_estimate/HYS14` (clock_model.py:22; apply_correction.py:11), `/data/wsd02/maleen_data/OOI-Data[-corrected]` (apply_correction.py:13-14; CM:46-47, 310, 536-537).

### 2e. What could serve as an oracle solver

Nothing in this pipeline is a hardware measurement. There is no GPS, PPS, cable-timing, or instrument-log source anywhere in the tracked text (README, CM, source; all read in full). The "ground truth" is a software estimate from ambient-noise cross-correlation against HYS12.

What is deterministic and present:

| piece | status | file |
|---|---|---|
| Δt(t) lookup for HYS14, 2022-08-10 to 2026-05-01, hourly, with trigger masking | present, deterministic, pure numpy/pandas | `clock_model.py:105-135` on `examples/HYS14/*.npy,*.csv` |
| Apply step: (raw MiniSEED, correction dir) → corrected MiniSEED | present, deterministic, numpy + obspy | `correct.py`, `apply_correction.py` |
| Measurement step: (raw HYS12 + HYS14 MHZ MiniSEED) → hourly Δt + triggers | absent as code; specified in prose with numeric parameters (CM sections 3-6, table in 2a) | none tracked |
| Uncertainty diagnostic (`chronos/scripts/uncertainty.py`) | absent | README.md:195-206 names it |

For an evaluation harness, the reference answer for HYS14 would be `delta_t_hourly_clean.npy` + `hour_times.npy` + `trigger_periods.csv`, with the authors' stated precision (σ_total ≈ 0.08 s typical, 0.17 s worst, README.md:158-159; picker quantum 0.125 s; trigger timing to ~1 h, CM:501-504). A reimplementation of the measurement from the documented recipe is possible but would not be byte-identical to the shipped file. Reference-station timing quality and the 30,496 vs 30,791 valid-hour discrepancy are NOT VERIFIED.

Code quirks a harness should know about (all read in source): Δt evaluated at UTC rather than apparent time in `_resample` (correct.py:112, 143, 158); a chunk is dropped if Δt is NaN at either end (126-127) or at output sample 0 (147-148); axis gaps not covered by a trigger are bridged linearly, e.g. the 41 h axis gap 2023-06-18T06 to 2023-06-20T00 lies between trigger rows 9 (2023-06-15) and 10 (2023-07-21) and is interpolated across; `manifest.csv` is appended, not replaced (apply_correction.py:158-163).

## 3. The other repositories

### sea-water-velocity (`<root>/sea-water-velocity/`)

Purpose: OOI RCA "Tier-3" VEL3D single-point current-meter data collection: retrieval from OOI, validation, conversion to MiniSEED/StationXML, staging to SeedLink or EarthScope Dropoff (README.md:1-8). Five reference designators, including `RS01SUM1-LJ01B-12-VEL3DB104` = `OO.HYS14` loc 20, 1 Hz Nobska MAVS-4, channels LOE/LON/LOZ/LKO (README.md:24-30); Endurance Nortek units at 8 Hz as `CZSHF`/`CZOFF` (README.md:13-14, 26-27). Data source: OOI M2M, `https://ooinet.oceanobservatories.org/api/m2m/12587/events/deployment/inv` and `/api/m2m/12576/sensor/inv`, plus OOI OPeNDAP and async-results servers (`VEL3D-data-collection/param/run_vel3d.txt:1-2, 13-14`). Entry points: `bin/run_ooi_requests.sh` → `bin/run_data_collection.sh` → `bin/OOI_data_request_and_convert_mseed.py` (`VEL3D-data-collection/README.md:101-105`); gap detection in `bin/gap_algorithms.py` with `gap_algo = anomaly` default (run_vel3d.txt:25); offline tools `bin/diagnose_timing.py`, `bin/temporal_anomaly_investigator.py` (README.md:109-110). Tracked data: three daily timestamp-quality tables `output/temporal_anomaly/metrics/{RS01SLBS,RS01SUM1,RS03AXBS}_vel3d_b_sample_variability.csv` (RS01SLBS: 4,295 daily rows from 2015-11-22; columns include `dt_true`, `n_gaps`, `jitter_*`), 975 PNG figures under `output/temporal_anomaly/figures/`, 5 StationXML under `output/xml/`. `VEL3D-data-collection/README.md` differs from the PREST one by two lines (diffed), and `CONVERSION_TODO.md:3-4` says the directory is a verbatim copy of `PREST-data-collection` still being adapted. Ground truth relevance: per-day sample-period and jitter metrics for current meters; nothing about seismometer clocks. No LICENSE file. HYS14 VEL3D coordinates 44.569173, −125.148073, elevation −777 m (`param/RS01SUM1_LJ01B_12_VEL3DB104_LOZ_20.txt:10-12`).

### absolute-seafloor-pressure (`<root>/absolute-seafloor-pressure/`)

Purpose: same pipeline for the PREST absolute pressure sensors ("Tidal Seafloor Pressure (Tsunameter 2,000 psia)", `PREST-data-collection/param/RS01SUM1_LJ01B_09_PRESTB102_LDO_10.txt:24`) at three RCA sites: `RS01SLBS-MJ01A-06-PRESTA101` = `OO.HYSB1`, `RS01SUM1-LJ01B-09-PRESTB102` = `OO.HYS14` loc 10, `RS03AXBS-MJ03A-06-PRESTA301` = `OO.AXBA1` (README.md:7-11); channels UDO/UK1 at 15 s and LDO/LK1 at 1 Hz, deployment epochs README.md:19-26. Data mirrored at EarthScope; FDSN `dataselect` and ObsPy examples README.md:35-64. OOI M2M endpoints in `bin/convert_mseed.py:80-82` and `bin/make_prest_params.py:36`. Cron schedule README.md:98-104; daily git push of metrics README.md:118-127. Tracked data: `output/diagnostics/metrics/{RS01SLBS,RS01SUM1,RS03AXBS}_metrics.csv` (31 daily rows each from 2025-01-01; columns `sp_calc, sp_fit, jitter_mean_ms, …`), `*_edge_cases.log`, `output/temporal_anomaly/metrics/*_variability.csv`, `dt_true_outliers.csv`, `fraction_missing.csv`, 3 StationXML. Also `param/botpt_params/` for BOTPT bottom-pressure-tilt at Axial (`RS03CCAL/RS03ECAL/RS03INT2`), not described in the README. HYS14 PREST coordinates 44.569218, −125.148115, elevation −773 m (`…_LDO_10.txt:12-14`). No LICENSE file. Ground truth relevance: none for seismic clocks.

### dive-index-hindcast (`<root>/dive-index-hindcast/`)

Purpose: MATLAB climatology of the "Dive Index" = significant wave height (m) × 10-m wind (kt) for ROV operations (README.md:16), thresholds 40 (loaded dive) and 70 (naked dive) (README.md:23-24; `DiveIndex_parameters.m:194`). Source: CAWCR WAVEWATCH III hindcast via OPeNDAP at `https://data-cbr.csiro.au/thredds/dodsC/catch_all/CMAR_CAWCR-Wave_archive/CAWCR_Wave_Hindcast_aggregate/gridded`, grid `glob_24m`, years 2006-2025, box lat 43-47, lon −131 to −123 (`DiveIndex_parameters.m:78-110`). Four sites: Slope Base 44.5096/−125.3983, Axial Base 45.8203/−129.7364, Oregon Offshore 44.36937/−124.95386, Oregon Shelf 44.63718/−124.30565 (lines 155-173); look-ahead 12 and 72 h (206). Entry: `P = DiveIndex_parameters; downloadCAWCRHindcast(P); run_DiveIndex_sites(P)` (README.md:75-77). Includes the output `RCA_DiveIndex_2006_2025.pdf` (11.9 MB). No Python, no OOI data, no LICENSE. Concept credited to Skip Denny, UW APL (README.md:12-13, 85-87). Not relevant to timing.

### coszo-hub.github.io (`<root>/coszo-hub.github.io/`)

Static site for coszo.org (`CNAME`), MIT licensed (LICENSE:1-3), generated by `build_pages.py` (184 KB) from `data/people.csv`, `data/data_channels.csv`, `data/blog.csv`; GitHub workflows `sync-blog.yml`, `sync-people.yml`, `update-ship-track.yml` (`bin/fetch_ship_track.py`, README.md:4-11). Archive PDFs under `assets/archives/` (white paper, workshop report, feasibility and trade studies). Reusable data: the two CSVs above (people, channel codes). README title reads "coszo-rcn.github.io".

## 4. Consolidated NOT VERIFIED list

| item | status |
|---|---|
| Public availability of `OO.HYS12`/`HYS14` MHZ at EarthScope | FDSN availability service returned "Service Unavailable" on both `service.iris.edu` and `service.earthscope.org` at 2026-09-14T21:23Z; not checked |
| coszo.org HTML equals repo `index.html` | same byte count, not diffed |
| Expansion of GSSM, CSCPR, PREST, BOTPT | not in files |
| Interpretation of the 1/480 s value quantization | inference |
| 30,496 retained (CM:166) vs 30,791 finite in shipped file | unexplained |
| Size of the UTC-vs-apparent Δt approximation in `_resample` | my estimate, ~5e-4 s |
| Instrument type of HYS14 ("OBS" in README.md:55; "BB seismometer + hydrophone, existing" in `sea-water-velocity/VEL3D-data-collection/OOI_channel_codes.md:29-31`; HYS11/12/13 called short-period there) | not reconciled |
| HYS12 timing quality | asserted only (CM:30-31) |
| Existence of chronos code anywhere | not public in `coszo-hub`; unknown elsewhere |
| Page count of `RCA_DiveIndex_2006_2025.pdf` | crude regex gave 16 |
