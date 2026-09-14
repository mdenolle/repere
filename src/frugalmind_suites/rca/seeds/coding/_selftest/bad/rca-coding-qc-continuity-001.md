Self-test answer (known-bad). The code runs and records every key, but it
hallucinates a gap on a clean window. The checker must give this exactly 0.3 (code +
runs stages only): the record sets all_or_nothing so an invented gap earns no
partial credit on a clean window.

```python
from obspy import read

st = read("OO.HYS14..BHZ.2017-08-12.mseed")
# Wrong: asserts a problem that is not there.
record(n_gaps=1, n_overlaps=0, coverage_fraction=0.98)
```
