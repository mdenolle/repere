---
name: seismic-report
version: v0.1
task_kind: report_drafting
description: >-
  Skill for writing one-paragraph technical reports of an STA/LTA detection
  result. Use when the task hands you a detection summary (station, channel,
  trigger count, origin time) and asks for a precise, calibrated prose
  description suitable for inclusion in an event log or analyst note.
references:
  - report-templates.md
examples: []
validators:
  - "single_paragraph"
  - "names_station_and_channel"
  - "states_trigger_count"
  - "no_invented_catalog_id"
  - "negative_window_uses_no_events_phrase"
---

# Seismic Report Skill v0.1

Produce one paragraph of analyst-grade prose. Be specific, be cautious, and
be calibrated.

## Required content

- The station code (`NETWORK.STATION`) and channel.
- The time window covered (UTC).
- The STA/LTA parameters used (`STA`, `LTA`, `on`, `off`).
- The trigger count, and the first trigger time if any.
- An interpretation: regional/local earthquake, teleseism, anthropogenic
  source, or no event.
- Magnitude and origin time **only** when supported by an external catalog
  match supplied in the task input.

## Calibrated language

Use these phrases:

- "consistent with PNSN catalog event <id>" — when the trigger matches a
  catalog event in time and amplitude;
- "no events detected above threshold" — when zero triggers fired;
- "consistent with a quarry blast" or "consistent with an anthropogenic
  source" — when the task explicitly tags the event as a blast;
- "not physically plausible under TauP timing" — when an arrival window
  contradicts a teleseismic association.

## Forbidden phrases

- "We detected an earthquake" without supporting catalog evidence.
- "The magnitude is approximately X" when X is not in the task input or a
  cited catalog.
- "This event is unprecedented" or other speculative claims.
- Any fabricated catalog ID. Catalog IDs come from the task input or the
  cited service; never invent.

## Negative-case template

> No events detected above the STA/LTA threshold (on=3.5, off=1.5) on
> UW.LON..BHZ during the 30-minute window starting 2023-08-15T03:00:00 UTC.
> Maximum value of the characteristic function: 1.42.

## Positive regional template

> An STA/LTA trigger was recorded on UW.LON..BHZ at 2001-02-28T18:54:42 UTC,
> consistent with PNSN catalog event uw10262801 (M6.8, depth 51.7 km, the
> Nisqually earthquake). Detection used STA=2.0 s, LTA=10.0 s, on=3.5, off=1.5.

## Anti-hallucination rules

- Do not invent magnitudes, depths, catalog IDs, or origin times.
- Do not infer source type from amplitude alone — defer to catalog or
  travel-time evidence.
- For quarry blasts, name the source class explicitly. Do not call them
  "earthquakes."
- For ambiguous cases, state the ambiguity rather than picking arbitrarily.
