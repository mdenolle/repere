# Matplotlib recipes for seismogram + STA/LTA plots

## Two-panel template

```python
import matplotlib.pyplot as plt

fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(10, 6))

ax1.plot(tr.times(), tr.data, color="black", linewidth=0.5)
ax1.set_ylabel("Counts")
ax1.set_title(f"{tr.stats.network}.{tr.stats.station} — {event_label}")

ax2.plot(tr.times(), cft, color="navy", linewidth=0.7)
ax2.axhline(on_thresh, color="grey", linestyle=":", linewidth=0.5)
ax2.set_xlabel("Time (s) since trace start")
ax2.set_ylabel("STA/LTA")

for on, _off in triggers:
    t_on = tr.times()[on]
    ax1.axvline(t_on, color="red", linestyle="--", linewidth=0.8)
    ax2.axvline(t_on, color="red", linestyle="--", linewidth=0.8)

fig.tight_layout()
fig.savefig("plot.png", dpi=120, bbox_inches="tight")
```

## Negative-window plot

When `triggers` is empty, draw the same two panels but skip the vertical
lines and add a subtitle:

```python
ax1.set_title(
    f"{tr.stats.network}.{tr.stats.station} — {event_label}\n"
    "no events detected above threshold"
)
```

## Style consistency

- Black waveform, navy STA/LTA, red dashed trigger lines.
- Default fonts; no `seaborn`-style overrides; SSIM penalises divergent
  styling.
- No extra annotations beyond the title and the trigger lines.
