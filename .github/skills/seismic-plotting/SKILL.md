---
name: seismic-plotting
version: v0.1
task_kind: plotting
description: >-
  Skill for producing reproducible seismogram-and-trigger plots with matplotlib.
  Use when the task is to render a two-panel figure (waveform on top, STA/LTA
  characteristic function on the bottom) with trigger onsets overlaid and a
  station/event title, and save the figure to a known PNG path for SSIM
  comparison against a golden image.
references:
  - matplotlib-recipes.md
examples: []
validators:
  - "saves_png_to_cwd"
  - "two_panels_present"
  - "title_includes_station_and_event"
  - "vertical_lines_at_triggers"
---

# Seismic Plotting Skill v0.1

This skill is narrow on purpose: produce a two-panel plot that downstream
SSIM scoring can compare against a golden reference.

## Required figure structure

- **Top panel:** waveform (`tr.times()` vs. `tr.data`), thin black line.
- **Bottom panel:** STA/LTA characteristic function on the same time axis.
- **Trigger overlay:** vertical dashed red lines at each trigger onset, drawn
  on **both** panels so the eye can align the trigger with the waveform
  feature that produced it.
- **Title:** include the station code (`NETWORK.STATION`) and the event label
  exactly as provided in the task input. Inconsistent titles fail the SSIM
  test even when the waveform is correct.

## Save location

Save the figure as `plot.png` in the **current working directory** (not a
subfolder, not `/tmp`, not the home directory). The harness sets `cwd` to a
sandbox; it does not search.

```python
fig.savefig("plot.png", dpi=120, bbox_inches="tight")
```

## DPI and size

Use `dpi=120` and `figsize=(10, 6)`. SSIM is scale-tolerant but high-DPI
deviations or extreme aspect ratios reduce the score.

## Anti-hallucination rules

- Do not plot synthetic data when the task provides a real stream.
- Do not invent trigger times. If the trigger array is empty, do not draw any
  vertical lines, and state in the title or a subtitle that no triggers were
  detected.
- Do not save under a different filename and then rename; SSIM looks for
  `plot.png` directly.
