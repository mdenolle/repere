---
name: dvv-processing
version: v0.1
task_kind: extraction
description: >-
  Domain skill for configuring an ambient-noise dv/v (relative seismic velocity
  change) monitoring pipeline. Use when the agent must choose the estimator,
  measurement frequency band, coda lapse-time window, stack length, reference
  strategy, and coherence gate for a monitoring target — volcano, fault,
  landslide, groundwater, cryosphere, or geothermal. The parameters are not
  independent: the band is set by the depth/scale of the target, and the coda
  window must follow from the band.
validators:
  - "band_matches_target_depth"
  - "window_consistent_with_band"
  - "explicit_estimator_choice"
---

# Configuring an ambient-noise dv/v pipeline

You are choosing six coupled parameters: `estimator`, `band`, `window`, `stack`,
`reference`, `gate`. The most common failure is picking them independently. They
are not independent.

## 1. The band is set by what you are trying to see

Frequency controls the **depth and scale** the measurement is sensitive to.
Surface waves at frequency *f* sample roughly the upper 1/3 of a wavelength, so
higher frequency = shallower and smaller.

| Target | Depth / scale | Band (Hz) |
|---|---|---|
| Volcanic edifice | upper few km, crack-rich | **0.4 – 1.0** |
| Fault / crustal damage | crustal, km-scale | **0.5 – 1.5** |
| Geothermal reservoir | km-scale | **0.5 – 2.0** |
| Groundwater / aquifer | tens of m – hundreds of m | **2.0 – 4.0** |
| Landslide body | shallow, m – tens of m | **4.0 – 12.0** |
| Cryosphere (ice/permafrost) | very shallow, m-scale | **4.0 – 14.0** |

Rule: **deep, large target → low band. Shallow, small target → high band.**
A band of 9–10 Hz on a volcano is not a conservative choice — it measures the
wrong rock.

## 2. The coda window follows from the band

You measure in the **coda** — the scattered late arrivals, which sample the
medium repeatedly and so amplify a small dv/v. The lapse-time window must start
after the ballistic/direct arrivals and end before the coda sinks into the noise
floor. Both limits scale with period, so the window scales **inversely with the
band**:

| Band (Hz) | Coda window (s) |
|---|---|
| 0.4 – 1.0 | **10 – 30** |
| 0.5 – 1.5 | **8 – 25** |
| 0.5 – 2.0 | **10 – 25** |
| 2.0 – 4.0 | **2 – 8** |
| 4.0 – 12.0 | **0.2 – 1.5** |
| 4.0 – 14.0 | **0.3 – 0.8** |

Rule: **low band → long, late window. High band → short, early window.**
A 10–30 s window with a 10 Hz band is empty coda: you are measuring noise.

## 3. Estimator

Default to **`stretching (TS)`**. It assumes a homogeneous relative velocity
change (dt/t constant across the coda), which is what dv/v monitoring is
defined as, and it is the most robust of the options when the coda is partially
decorrelated or the SNR is modest — the normal condition for ambient noise.

Use MWCS/WCS-family estimators only when you specifically need a
frequency-dependent or lapse-dependent dt/t; they are noisier at low SNR and
will not improve a routine monitoring configuration.

## 4. Stack, reference, gate

- **`stack`**: days of cross-correlation stacked to raise SNR. **10** days for
  quiet, slowly-varying targets (volcano, fault, groundwater, geothermal);
  **5** days when the signal is fast and large and you cannot afford to smear
  it in time (landslide, cryosphere). More stacking = better SNR but worse time
  resolution. That trade is the whole choice.
- **`reference`**: **`fixed`** — compare every day to a single fixed reference
  period. A moving/trailing reference subtracts out exactly the slow trend you
  are trying to measure.
- **`gate`**: **`true`** — gate on waveform coherence so decorrelated,
  low-quality days are rejected rather than injecting spurious dv/v. Turning the
  gate off is how you get a beautiful time series of garbage.

## 5. Sanity checks before returning

- Does the band match the target's depth (§1)?
- Does the window match the band (§2)? Cross-check both tables.
- Is the estimator explicitly chosen, not defaulted silently?
- Is `reference` fixed and `gate` on, unless you can justify otherwise?

Return **only** the JSON object with the six keys. Do not narrate.
