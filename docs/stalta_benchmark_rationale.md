# Why the First Benchmark Is STA/LTA Event Detection

The first Repère benchmark is intentionally built around STA/LTA event detection because it is the most basic end-to-end earthquake seismology coding workflow: identify whether waveform data contain an event, fetch the relevant data, run a standard detector, and explain the likely source using seismological constraints.

This benchmark asks a practical question: **can a coding agent write correct seismology code for the simplest earthquake detection pipeline without overfitting to generic Python patterns?**

## Why STA/LTA is the right first test

STA/LTA is a useful first benchmark because it is:

1. **Canonical.** Short-term-average / long-term-average triggering is one of the first detection methods taught in observational seismology.
2. **Small but complete.** It requires data access, signal processing, event detection, plotting, and interpretation.
3. **Easy to score in pieces.** Each stage can be graded independently: JSON extraction, waveform fetch code, trigger code, plot generation, and report text.
4. **Hard enough to expose non-domain agents.** A generic coding agent may write syntactically valid Python while choosing impossible stations, wrong channels, inappropriate filters, invalid time windows, or hallucinated event explanations.
5. **Scientifically interpretable.** Failures are meaningful: missed arrivals, false positives on quiet windows, local-vs-teleseismic confusion, or unsupported catalog claims.

## What the benchmark is testing

The STA/LTA suite is not only testing whether code runs. It is testing whether an agent can implement a minimal seismological reasoning loop:

1. **Translate intent into a waveform request.**
   - Identify network, station, channel, location code, start time, and end time.
   - Use a physically sensible time window for the event class.

2. **Fetch waveform data.**
   - Use ObsPy and FDSN clients correctly.
   - Avoid hardcoded local-only paths or fake data.
   - Preserve enough metadata to interpret the trace.

3. **Detect an event.**
   - Detrend and filter the waveform appropriately.
   - Run STA/LTA with event-appropriate parameters.
   - Record trigger counts and first-trigger information.
   - Avoid hallucinating detections in quiet windows.

4. **Plot the detection.**
   - Show the waveform and characteristic function.
   - Mark trigger onsets.
   - Label station, channel, and event context clearly.

5. **Explain the likely source.**
   - If the event is local or regional, identify the regional network and query nearby regional catalogs.
   - If the event is teleseismic, search a global catalog over the preceding 1-2 hours, apply a magnitude threshold large enough to be visible at the station, and compute plausible arrival windows.
   - Use ObsPy TauP travel-time curves to test whether predicted arrivals are consistent with the observed window.
   - Distinguish earthquakes from anthropogenic events when catalog metadata or context support that distinction.

## Local/regional event explanation

For local or regional candidates, the agent should be able to:

- Select stations from an appropriate regional network.
- Query a regional catalog such as PNSN or another local FDSN event service.
- Search near the station/event region and time window.
- Compare catalog origin time, distance, and magnitude against the observed trigger.
- Report uncertainty if the catalog match is ambiguous.

A strong answer should avoid claiming a local earthquake solely because STA/LTA triggered. The report should connect the trigger to catalog evidence or explicitly say that no catalog match was found.

## Teleseismic event explanation

For teleseismic candidates, the agent should be able to:

- Query a global earthquake catalog for events in the previous 1-2 hours.
- Filter to a magnitude range likely visible at the station, initially around magnitude 4+ with event- and distance-dependent judgment.
- Use ObsPy TauP to calculate travel-time curves for plausible seismic phases.
- Compare predicted arrivals with the observed waveform window.
- Explain why the arrival time is or is not physically plausible.

This is where the benchmark moves beyond generic coding. The agent must know that a large distant earthquake can arrive well after origin time and that arrival plausibility depends on distance, phase, depth, and velocity model.

## Current subtests

The current v0.1 public suite contains five subtests per event:

| Subtest | Purpose | Current scoring approach |
|---|---|---|
| Intent extraction | Convert a natural-language seismology request into an FDSN waveform query. | JSON field matching with time tolerances. |
| Fetch code generation | Write ObsPy code that fetches waveform data. | Static code checks plus sandboxed execution artifacts. |
| Trigger code generation | Write STA/LTA detection code for an in-memory stream. | Static code checks plus recorded trigger artifacts. |
| Plot generation | Produce a waveform and trigger plot. | SSIM comparison against approved goldens when available. |
| Report drafting | Explain detections or non-detections. | Catalog-claim rubric with false-positive penalties. |

Future versions should add explicit source-explanation subtests:

1. **Regional catalog association.** Given a trigger and station, search a regional catalog and justify whether a nearby event explains it.
2. **Teleseismic association.** Given a trigger and station, query a global catalog, compute TauP travel times, and determine whether a candidate earthquake plausibly explains the arrival.
3. **No-event / noise rejection.** Confirm that quiet windows do not become hallucinated earthquakes.
4. **Anthropogenic discrimination.** Identify quarry blasts or other non-tectonic events when catalog or context supports the interpretation.

## When to develop a SeismoDataAgent skill file

A `SeismoDataAgent` skill file is useful when the seismology workflow becomes reusable agent guidance rather than just benchmark content.

Develop the skill **after** these conditions are true:

1. The STA/LTA benchmark scope is stable enough that the desired agent behavior is clear.
2. At least a few public examples and private golden examples have been manually reviewed.
3. The expected workflow is repeated across tasks: waveform request, FDSN fetch, preprocessing, STA/LTA trigger, catalog association, TauP plausibility, and report.
4. You want to evaluate a domain-assisted coding agent, not only a raw general coding agent.
5. You can version the skill and treat it as part of the model/agent configuration in leaderboard metadata.

Do **not** create the skill too early if the goal is to measure a baseline general coding agent. A skill changes the agent's capabilities and should be treated as an experimental condition. The leaderboard should distinguish, for example, `generic-coding-agent` from `SeismoDataAgent+skill-v0.1`.

A first draft skill now lives under `.github/skills/seismo-data-agent/SKILL.md` and should be invoked only for seismology data-analysis tasks. It contains concise workflow instructions, common ObsPy patterns, catalog/TauP decision rules, and explicit anti-hallucination requirements. It should not include private golden answers.

When this skill is used in an eval, the result should be recorded as a separate leaderboard condition, for example `SeismoDataAgent+skill-v0.1-draft`. See `docs/leaderboard_conditions.md` for the result metadata fields.
