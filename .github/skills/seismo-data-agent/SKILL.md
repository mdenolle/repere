---
name: seismo-data-agent
version: v0.1-draft
task_kind: code_generation
description: "Legacy end-to-end seismology coding skill. Superseded by `stalta-detection` v0.2. Kept for back-compat with leaderboard rows tagged `SeismoDataAgent+skill-v0.1-draft`. New work should use stalta-detection."
references: []
examples: []
validators:
  - "no_fabricated_catalog_ids"
---

# SeismoDataAgent Skill v0.1-draft

Use this skill for earthquake seismology coding tasks where the agent must fetch waveform data, detect possible seismic events, and explain the source using catalog and travel-time evidence. This skill is a domain workflow guide, not a source of benchmark answers.

## Prime directive

Write reproducible seismology code that is physically plausible, explicit about uncertainty, and resistant to hallucinated event claims. Prefer a cautious report with clear evidence over a confident but unsupported earthquake interpretation.

## Standard workflow

1. **Clarify the analysis target.**
   - Identify station, network, channel, location code, start time, end time, and sampling assumptions.
   - Preserve UTC time handling and avoid local-time ambiguity.
   - If station metadata are missing, query inventory or state that metadata are unavailable.

2. **Fetch waveform data with ObsPy.**
   - Use `obspy.clients.fdsn.Client` for waveform and event services.
   - Prefer explicit clients such as `Client("IRIS")`, `Client("USGS")`, or a regional service when known.
   - Fetch station inventory when response removal, coordinates, or distance calculations are required.
   - Never fabricate waveform data, station metadata, or catalog events.

3. **Preprocess before detection.**
   - Merge, trim, detrend, taper, and filter before STA/LTA.
   - Choose filter bands appropriate to the target:
     - local/regional high-frequency events: often around 1-20 Hz;
     - teleseismic long-period arrivals: lower-frequency bands may be needed.
   - State preprocessing parameters in the output report.

4. **Run STA/LTA carefully.**
   - Use `classic_sta_lta` or another explicit ObsPy trigger method.
   - Convert STA/LTA windows from seconds to sample counts using the trace sampling rate.
   - Record trigger count, first trigger sample/time, and thresholds.
   - Treat zero-trigger windows as meaningful negative evidence.

5. **Associate with a source hypothesis.**
   - Do not claim an earthquake solely because a trigger exists.
   - Test at least these hypotheses when relevant:
     - local/regional earthquake;
     - teleseismic earthquake;
     - anthropogenic event such as quarry blast;
     - no event/noise/transient artifact.

## Regional/local earthquake association

For local or regional candidates:

- Use the regional network and catalog when known, for example PNSN for Pacific Northwest examples.
- Search a catalog around the waveform time window and plausible station/event region.
- Compare origin time, epicentral distance, magnitude, depth, and station geometry with observed trigger time.
- If no matching catalog event is found, say so; do not invent one.
- If multiple candidates exist, rank them by timing and distance consistency and report ambiguity.

## Teleseismic association

For teleseismic candidates:

- Query a global catalog for the preceding 1-2 hours relative to the observed arrival window.
- Start with magnitude >= 4.0 only as a coarse screen; raise the threshold for distant or noisy stations when appropriate.
- Use station coordinates and event coordinates to compute distance.
- Use ObsPy TauP, such as `obspy.taup.TauPyModel`, to predict plausible phase arrivals.
- Compare observed trigger time with predicted arrivals for phases such as P, S, PP, SS, and surface-wave windows as appropriate.
- Explain whether the candidate is physically plausible under the selected velocity model.

## Reporting requirements

Reports should include:

- station/network/channel and time window;
- preprocessing and STA/LTA parameters;
- trigger count and first trigger time, if any;
- catalog search source and time/radius/magnitude filters;
- TauP model and predicted phase timing for teleseismic claims;
- final interpretation with uncertainty.

Use language such as:

- "consistent with" when evidence supports a candidate;
- "no catalog match found" when search fails;
- "not physically plausible under TauP timing" when arrival windows do not match;
- "no event detected above threshold" for negative windows.

## Anti-hallucination rules

- Do not fabricate catalog IDs, magnitudes, coordinates, stations, channels, or arrival times.
- Do not label a trigger as a tectonic earthquake without catalog or travel-time support.
- Do not ignore negative cases; quiet windows are first-class results.
- Do not commit private golden answers, hidden benchmark labels, or manually approved artifacts into skill content.
- If network calls are unavailable, write code that would perform the query and explicitly mark the result as unverified.

## Suggested ObsPy imports

Use these patterns when appropriate:

```python
from obspy import UTCDateTime
from obspy.clients.fdsn import Client
from obspy.signal.trigger import classic_sta_lta, trigger_onset
from obspy.taup import TauPyModel
```

## Leaderboard condition

Runs using this skill should be recorded as a separate condition, for example:

```json
{
  "model_id": "example-model",
  "agent_condition": "SeismoDataAgent+skill-v0.1-draft",
  "skill_name": "seismo-data-agent",
  "skill_version": "v0.1-draft"
}
```

Do not compare `SeismoDataAgent+skill-v0.1-draft` directly against a raw `generic-coding-agent` condition without labeling the condition difference on the leaderboard.
