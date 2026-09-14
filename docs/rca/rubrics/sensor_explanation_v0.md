# Rubric: sensor explanation (v0, TODO)

Used by `rca-sensor-explain-hys12-vs-hys14-003`. Every criterion is binary.
No judge score may be reported until two raters have rated the calibration
set and the judge's agreement with them is published (DESIGN.md §4.4).

TODO(co-author, RCA engineer + PI): write 5 to 8 criteria. Suggested shape,
to be replaced:

| # | Criterion (yes/no) | Notes |
|---|---|---|
| 1 | Distinguishes broadband (HYS14, CMG-1T 360 s) from short-period (HYS12, CMG-6TF) | from the EarthScope station metadata |
| 2 | Names at least one co-located non-seismic sensor at HYS14 (hydrophone, accelerometer, pressure, current meter) | |
| 3 | Mentions the HYS14 timing caveat and that a correction exists | chronfix |
| 4 | Gives a use-case rule (when to prefer which) that is consistent with 1 | |
| 5 | Invents no sensor, channel or date | any fabrication fails this criterion |

Calibration set: `TODO` (path to >= 10 rated answers). Raters: `TODO`.
Judge model pin: `TODO`. Agreement: `TODO` (kappa).
