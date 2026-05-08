# STA/LTA window and threshold tuning

## Default starting points

| Source class           | STA (s) | LTA (s) | on  | off |
|------------------------|--------:|--------:|----:|----:|
| Local (high-frequency) | 0.5     | 8       | 4.0 | 1.5 |
| Regional               | 2.0     | 10      | 3.5 | 1.5 |
| Teleseism              | 5.0     | 60      | 3.0 | 1.5 |
| Volcanic (LP)          | 1.0     | 12      | 3.5 | 1.5 |

These are starting points, not optima. Tune to the noise floor of the station.

## Heuristics

- STA should be roughly the duration of the shortest arrival you want to
  detect; LTA should be a few multiples of the longest.
- For high-frequency local events (M ~1–3 nearby), STA ≤ 1 s and LTA ≤ 10 s
  works well.
- For teleseismic P-wave arrivals at regional stations, STA of 5–10 s and LTA
  of 60–120 s avoids amplitude bias from microseism.
- on-threshold ≥ 3.0 controls false-trigger rate; below 2.5 you will trigger
  on transients constantly.
- off-threshold should always be < on-threshold; 1.5 is conventional.

## When to switch from `classic_sta_lta` to alternatives

- `recursive_sta_lta`: when you need a streaming/online detector or want
  exponential averaging instead of boxcar.
- `z_detect`: better for impulsive arrivals on quiet stations.
- ML detectors (PhaseNet, EQTransformer): preferred when ground truth is
  available; STA/LTA remains the right baseline for evaluation.

## Negative cases

If the window has zero triggers above threshold, that is the result. Do not
lower the threshold to "find something." Report:

- the threshold used,
- the maximum value of the characteristic function,
- and that no value crossed the on-threshold.
