# ObsPy recipes for STA/LTA

## Fetch + preprocess + detect (regional)

```python
from obspy import UTCDateTime
from obspy.clients.fdsn import Client
from obspy.signal.trigger import classic_sta_lta, trigger_onset

client = Client("IRIS")
t0 = UTCDateTime("2001-02-28T18:54:32.8")
st = client.get_waveforms(
    network="UW", station="LON", location="", channel="BHZ",
    starttime=t0 - 60, endtime=t0 + 540,
    attach_response=False,
)
st.merge(method=1, fill_value=0)
st.detrend("demean").detrend("linear").taper(0.05)
st.filter("bandpass", freqmin=1.0, freqmax=20.0, corners=4, zerophase=True)
tr = st[0]

sta_n = int(2.0 * tr.stats.sampling_rate)
lta_n = int(10.0 * tr.stats.sampling_rate)
cft = classic_sta_lta(tr.data, sta_n, lta_n)
triggers = trigger_onset(cft, 3.5, 1.5)
```

## Fetch + detect (teleseism)

For long-period arrivals, increase LTA, lower the on-threshold, and use a
broader bandpass:

```python
st.filter("bandpass", freqmin=0.02, freqmax=0.5, corners=4, zerophase=True)
sta_n = int(5.0 * tr.stats.sampling_rate)
lta_n = int(60.0 * tr.stats.sampling_rate)
cft = classic_sta_lta(tr.data, sta_n, lta_n)
triggers = trigger_onset(cft, 3.0, 1.5)
```

## Plot

```python
import matplotlib.pyplot as plt
fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(10, 6))
ax1.plot(tr.times(), tr.data, color="black", linewidth=0.5)
ax2.plot(tr.times(), cft, color="navy")
for on, _ in triggers:
    t_on = tr.times()[on]
    ax1.axvline(t_on, color="red", linestyle="--")
    ax2.axvline(t_on, color="red", linestyle="--")
ax1.set_ylabel("Counts")
ax2.set_ylabel("STA/LTA")
ax2.set_xlabel("Time (s) since trace start")
ax1.set_title(f"{tr.stats.network}.{tr.stats.station} — STA/LTA detection")
fig.savefig("plot.png", dpi=120, bbox_inches="tight")
```

## TauP cross-check

```python
from obspy.taup import TauPyModel
from obspy.geodetics import locations2degrees

dist_deg = locations2degrees(38.297, 142.373, 46.7, -122.0)  # Tohoku → LON
model = TauPyModel(model="iasp91")
arrivals = model.get_travel_times(
    source_depth_in_km=29.0, distance_in_degree=dist_deg,
    phase_list=["P", "PP", "S", "SS"],
)
```

## Common mistakes

- Forgetting to convert STA/LTA windows from seconds to samples.
- Skipping `merge` on multi-segment streams; STA/LTA on a stream with gaps is
  meaningless.
- Skipping `attach_response=True` and then attempting `remove_response()`.
- Using regional STA/LTA windows for teleseisms (fails to trigger because the
  characteristic function is dominated by short-period microseism).
