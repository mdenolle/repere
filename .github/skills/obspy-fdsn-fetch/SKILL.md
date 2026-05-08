---
name: obspy-fdsn-fetch
version: v0.1
task_kind: code_generation
description: >-
  Narrow-focus skill for writing reproducible ObsPy code that fetches waveforms
  and station metadata from FDSN web services. Use whenever the task is to
  download waveforms for a specific network/station/channel/time window from
  IRIS, USGS, or a regional FDSN endpoint.
references:
  - fdsn-clients.md
examples: []
validators:
  - "uses_fdsn_Client"
  - "uses_get_waveforms_or_get_stations"
  - "explicit_starttime_endtime"
---

# ObsPy FDSN Fetch Skill v0.1

Use this skill for tasks limited to retrieving waveforms or station metadata
from an FDSN web service. The skill does not cover detection, plotting, or
reporting — only the fetch itself and minimal post-fetch validation.

## Workflow

1. Build a `Client`. Prefer named services:
   - `Client("IRIS")` for global and most US regional data;
   - `Client("USGS")` when the task references USGS event/waveform services;
   - regional FDSN endpoints (NCEDC, SCEDC) for California-specific tasks.
2. Convert `starttime` and `endtime` to `obspy.UTCDateTime`.
3. Call `client.get_waveforms(network, station, location, channel,
   starttime, endtime, attach_response=False)`. Set `attach_response=True`
   only if the downstream task removes instrument response.
4. Verify the result is a non-empty `Stream`. If empty, raise or return a
   structured error — do not silently fabricate traces.
5. For metadata-only tasks, use `client.get_stations(...)` with `level="response"`
   when responses are needed, else `level="channel"`.

## Anti-hallucination rules

- Do not invent station codes, channel codes, or time windows.
- Do not fabricate sampling rates, instrument responses, or trace data.
- If the FDSN call would fail, write the call as it should be issued and let
  it fail at runtime; document the expected failure mode in a comment.

## Required imports

```python
from obspy import UTCDateTime
from obspy.clients.fdsn import Client
```

## Minimal positive example

```python
client = Client("IRIS")
t0 = UTCDateTime("2001-02-28T18:54:32.8")
st = client.get_waveforms(
    network="UW", station="LON", location="", channel="BHZ",
    starttime=t0 - 60, endtime=t0 + 540,
    attach_response=False,
)
```
