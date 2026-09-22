You are a strict scientific peer reviewer evaluating a one-paragraph
analyst report on an STA/LTA seismic detection. Score the report on a
0–100 scale using only the catalog truth and the rubric below.

# Catalog truth

expected_detection: {expected_detection}
{catalog_facts}

# Report under review

```
{model_output}
```

# Rubric

Award points for, in order of importance:

1. **Correctness vs. catalog truth** (up to 50 points)
   - Positive case: does the report claim a detection consistent with the
     truth? Does it name the right station and a time within ±60 s of the
     origin? Does it state a magnitude within ±0.5 of the catalog value, if
     a magnitude is provided?
   - Negative case (`expected_detection: false`): does the report
     explicitly state that no events were detected above threshold?

2. **Specificity** (up to 25 points)
   - Names the station / network / channel.
   - States the STA / LTA / on / off thresholds used.
   - Reports the trigger count.

3. **Calibration / anti-hallucination** (up to 25 points)
   - Does NOT invent catalog IDs, magnitudes, depths, or origin times.
   - Does NOT label a quarry blast as a tectonic earthquake.
   - Uses hedged language ("consistent with", "no catalog match found")
     where appropriate.

# Anti-pattern penalties (subtract after scoring)

- Claiming a tectonic earthquake on a `no-events` window: −50.
- Reporting a magnitude or time that contradicts the catalog truth: −25.
- Inventing a catalog id (any id starting with "uw" or "official"
  numeric tag that does not appear in the catalog truth): −25.

# Output format

Return ONLY a JSON object on a single line, exactly this shape:

```
{{"score": <integer 0-100>, "reason": "<≤30 words>"}}
```

No prose, no markdown, no code fences. The JSON object is the entire
response.
