# Worked example: PNSN quiet day (negative case)

**Input**
- Station: UW.LON..BHZ
- Window: 2023-08-15T03:00:00 UTC, 30 minutes wide
- No event expected.

**Expected workflow output**

1. Fetch the 30-minute window.
2. Bandpass 1–20 Hz, demean/detrend/taper.
3. STA=2.0 s, LTA=10.0 s, on=3.5, off=1.5.
4. Trigger count: 0 (or possibly 1 if a regional teleseism slipped in;
   default is 0).
5. Report: "No events detected above STA/LTA threshold (on=3.5, off=1.5)
   on UW.LON..BHZ during the 30-minute window starting 2023-08-15T03:00:00 UTC.
   Maximum STA/LTA value: <value>."

**What success looks like**
- Trigger count reported as exactly 0.
- Report explicitly states "no events detected."
- No invented catalog ID, magnitude, or origin time.

**What failure looks like**
- Reporting an earthquake of any magnitude.
- Reporting "a tectonic event was observed."
- Lowering the threshold until something triggers.

This is the most important case in the suite. A model that hallucinates
detections on quiet windows is unfit for monitoring use. Report negative
results with the same care as positive ones.
