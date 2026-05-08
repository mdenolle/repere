---
name: stalta-detection
version: v0.2
task_kind: code_generation
description: >-
  End-to-end seismology workflow skill for STA/LTA event detection. Use when the
  agent must fetch waveform data, preprocess it, run a short-term-average over
  long-term-average trigger, associate any triggers with a regional/teleseismic
  catalog, and report results with calibrated uncertainty. Covers positive
  detections (regional/local earthquakes, teleseisms), anthropogenic sources
  (quarry blasts), and explicitly negative cases (noise days, no-trigger windows).
references:
  - pnsn-catalog.md
  - obspy-recipes.md
  - stalta-tuning.md
examples:
  - nisqually-detection.md
  - quiet-window.md
validators:
  - "no_fabricated_catalog_ids"
  - "uses_classic_sta_lta"
  - "explicit_filter_band"
  - "negative_window_explicitly_reported"
---

# STA/LTA Detection Skill v0.2

End-to-end guidance for STA/LTA-based seismic event detection. Use this skill
when the task requires fetching waveform data, detecting triggers, and
explaining the source with catalog or travel-time evidence. This skill is a
domain workflow guide, not a source of benchmark answers.

## Prime directive

Write reproducible seismology code that is physically plausible, explicit about
uncertainty, and resistant to hallucinated event claims. Prefer a cautious
report with clear evidence over a confident but unsupported earthquake
interpretation. Negative results — quiet windows, no triggers above threshold —
are first-class outputs, not failures.

## Standard workflow

1. **Clarify the analysis target.**
   - Identify network, station, location code, channel, start time, end time,
     and sampling assumptions.
   - Preserve UTC time handling and avoid local-time ambiguity.
   - If station metadata are missing, query inventory or state explicitly that
     metadata are unavailable.

2. **Fetch waveform data with ObsPy.**
   - Use `obspy.clients.fdsn.Client`. Prefer named services such as
     `Client("IRIS")`, `Client("USGS")`, or a regional FDSN endpoint when the
     task references a regional network (PNSN for the Pacific Northwest, NCEDC
     for Northern California, etc.).
   - Fetch station inventory when response removal, coordinates, or distance
     calculations are required.
   - Never fabricate waveforms, station metadata, or catalog events. If the
     network is unavailable, write code that would perform the query and mark
     the result as unverified.

3. **Preprocess before detection.**
   - Merge, trim, detrend, taper, and filter before STA/LTA.
   - Filter band depends on target:
     - local/regional high-frequency events: ~1–20 Hz bandpass.
     - teleseismic long-period arrivals: 0.02–0.5 Hz or appropriate broadband.
   - Always state preprocessing parameters in the output report.

4. **Run STA/LTA carefully.**
   - Use `obspy.signal.trigger.classic_sta_lta` (or `recursive_sta_lta` when
     justified). Convert STA/LTA windows from seconds to sample counts using
     the trace sampling rate.
   - Record trigger count, first trigger sample/time, and thresholds.
   - Treat zero-trigger windows as meaningful negative evidence.

5. **Associate with a source hypothesis.**
   Test these hypotheses when relevant:
   - local/regional earthquake (catalog match within distance/time tolerance);
   - teleseismic earthquake (catalog M ≥ 4.0 within prior 1–2 hours, plausible
     phase arrivals via TauP);
   - anthropogenic event (quarry blast, mine blast, controlled source);
   - no event / noise / instrumental transient.
   Do not claim an earthquake solely because a trigger exists.

## Regional/local earthquake association

- Use the regional network catalog (PNSN for the Pacific Northwest examples in
  this benchmark).
- Search a catalog around the waveform time window and plausible station
  region.
- Compare origin time, epicentral distance, magnitude, depth, and station
  geometry with observed trigger time.
- If no matching catalog event is found, say so. Do not invent one.
- If multiple candidates exist, rank them by timing and distance consistency
  and report ambiguity.

## Teleseismic association

- Query a global catalog for the preceding 1–2 hours.
- Use a coarse magnitude screen (e.g. M ≥ 4.0); raise it for distant or noisy
  stations.
- Use `obspy.taup.TauPyModel` with `iasp91` or `ak135` to predict arrivals for
  P, S, PP, SS, and surface-wave windows.
- Compare observed trigger time with predicted arrivals.
- State whether the candidate is physically plausible under the velocity model.

## Reporting requirements

Every report must include:

- station/network/channel and time window;
- preprocessing and STA/LTA parameters;
- trigger count and first trigger time, if any;
- catalog search source and time/radius/magnitude filters;
- TauP model and predicted phase timing for teleseismic claims;
- final interpretation with uncertainty.

Use language like:

- "consistent with" when evidence supports a candidate;
- "no catalog match found" when search fails;
- "not physically plausible under TauP timing" when arrival windows do not
  match;
- "no events detected above threshold" for negative windows.

## Anti-hallucination rules

- Do not fabricate catalog IDs, magnitudes, coordinates, stations, channels,
  or arrival times.
- Do not label a trigger as a tectonic earthquake without catalog or
  travel-time support.
- Do not ignore negative cases; quiet windows are first-class results.
- Do not commit private golden answers, hidden benchmark labels, or manually
  approved artifacts into skill content.
- If network calls are unavailable, write code that would perform the query
  and explicitly mark the result as unverified.

## Suggested ObsPy imports

```python
from obspy import UTCDateTime
from obspy.clients.fdsn import Client
from obspy.signal.trigger import classic_sta_lta, trigger_onset
from obspy.taup import TauPyModel
```

## Leaderboard condition

Runs using this skill should record:

```json
{
  "model_id": "<model>",
  "agent_condition": "stalta-detection+skill-v0.2",
  "skill_name": "stalta-detection",
  "skill_version": "v0.2"
}
```

Do not compare a `stalta-detection+skill-v0.2` row directly against a raw
`generic-coding-agent` row without labelling the condition difference on the
leaderboard.
