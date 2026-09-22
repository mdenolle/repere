Self-test answer (known-good). This is a harness check, not a model output:
the checker must give this 1.0 (ABC T.8/T.9). Kept beside the seed so a
co-author editing the record re-runs it.

```python
from obspy import read, UTCDateTime

st = read("OO.HYS14..BHZ.2017-08-12.mseed")
t0 = UTCDateTime("2017-08-12T00:00:00")
t1 = UTCDateTime("2017-08-12T00:02:00")

gaps = st.get_gaps()
n_gaps = sum(1 for g in gaps if g[6] > 0)
n_overlaps = sum(1 for g in gaps if g[6] < 0)

covered = 0.0
for tr in st:
    a = max(tr.stats.starttime, t0)
    b = min(tr.stats.endtime, t1)
    if b > a:
        covered += float(b - a)
coverage_fraction = min(1.0, covered / float(t1 - t0))

record(n_gaps=n_gaps, n_overlaps=n_overlaps, coverage_fraction=coverage_fraction)
print("clean" if n_gaps == 0 and n_overlaps == 0 else "gaps found")
```
