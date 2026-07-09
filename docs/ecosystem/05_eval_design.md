# Multi-difficulty synthetic evaluations for seismology agents

Part 5 of the ecosystem analysis. This extends FrugalMind's existing design (parametric truth set, negative-case discipline, scorability spectrum T0→T4, private goldens) from the STA/LTA reference suite to the full ecosystem. The organizing idea: **the modeling stack is the eval generator for the observational stack.** Simulators produce waveforms with exact ground truth (origin, mechanism, arrivals, structure); the observational chain must recover it; scoring is deterministic (T0) almost everywhere.

## Why synthetic, why parametric

Every famous sequence (Ridgecrest, Tohoku, L'Aquila) is in every LLM's training data, so real-data evals measure memory as much as competence. Parametric generators — the `events.yaml` idea generalized to `scenarios.yaml` — produce unlimited, contamination-free items with private seeds, and difficulty becomes a set of continuous knobs rather than a hand-curated label. TRACE's internal protocol is the only prior art for graded seismology-agent evaluation, and it is observational, non-synthetic, and unreleased. A public, generator-backed, difficulty-laddered harness is an open slot.

## Difficulty axes (the knobs)

1. **Signal**: SNR, event magnitude, noise realism (white → colored → real noise injection from STEAD/SCEDC quiet periods).
2. **Scene complexity**: single event → overlapping events → swarm rates; mainshock+aftershock density; negative cases (no event, teleseism-only, cultural noise) as first-class items.
3. **Network**: dense/well-azimuthed → sparse → one-sided; station dropouts; wrong/missing response metadata (deliberate metadata faults test the QC step).
4. **Model mismatch**: truth simulated in model A, tools given model B (velocity perturbation %, unmodeled Moho, 3D truth vs 1D assumption). This axis measures scientific judgment, not plumbing.
5. **Tool difficulty**: clean Python API → CLI+config → legacy fixed-format codec → HPC multi-step (interface tiers from [01_ecosystem_map.md](01_ecosystem_map.md)).
6. **Autonomy**: fully specified prompt → underspecified goal (agent must choose tools/parameters) → adversarial (a plausible-looking wrong path is available; e.g., a picker whose training domain mismatches the data).

## Generator inventory (all open, mostly laptop-scale)

| Generator | Ground truth provided | Cost |
|---|---|---|
| Syngine REST / Instaseis | teleseismic waveforms; exact MT, depth, arrivals (TauP) | zero install |
| Pyrocko fomosto + Greens Mill stores | regional waveforms + statics; any source type; strain (DAS) | laptop |
| CPS / PyFK | 1D layered synthetics; dispersion + eigenfunctions via disba | seconds |
| SPECFEM2D / SPECFEM++ | 2D full wavefield; adjoint kernels; checkerboards | laptop |
| SW4 / OpenSWPC | 3D regional with topography; SAC out; no meshing | workstation |
| Deepwave | differentiable FWI truth models (Marmousi-class) | laptop GPU |
| QDYN / tandem (BP1-QD) | multi-cycle synthetic catalogs with known rate-state physics | laptop (2D) |
| SeisSol (deferred) | dynamic rupture scenarios; kinematic SRF export | HPC |
| noisi / GF-store correlations | CCFs with prescribed source distributions; known dispersion | laptop |

Community references double as fixed goldens: LOH.1–3 (SISMOWINE), SCEC TPV suite, SEAS BP1–7 curves, Lamb's problem analytic, PREM/TauP travel times, Kagan angle vs GCMT for real-event spot checks.

## Suite ladder

Each suite has levels L0–L4 on shared conventions: L0 = single tool call, clean data, full spec (tests tool competence); L1 = same with realistic noise + minor spec gaps; L2 = multi-step chain, parameter choices scored; L3 = model mismatch + negative cases + adversarial paths (tests judgment); L4 = underspecified scientific goal, orchestration scored via call-DAG (Family 3). Scoring stays T0/T1 through L3; L4 mixes DAG scoring with rubric judges.

**S1 `pick_associate_locate` (Family 2, new).** Generator: fomosto regional scenes. Truth: arrivals, hypocenters. Scores: pick residual distribution, association precision/recall (event membership), hypocenter error km, uncertainty calibration (does the reported posterior cover truth?). L3 injects velocity mismatch and metadata faults; L4 asks "build me a catalog for this deployment" cold.

**S2 `relocate` (Family 2, new).** Generator: clustered synthetic sequences (two parallel faults, given hypocenters + correlated waveforms). Chain: dt.ct/dt.cc generation → HypoDD or GrowClust via codecs. Score: inter-event geometry recovery (fault-plane separation resolved or not — a binary scientific outcome), residual stats. This suite doubles as CI for the relocation glue release.

**S3 `source_mt` (Family 2, new).** Generator: Syngine/fomosto with known MT. Chain: GF retrieval → MTUQ/Grond. Score: Kagan angle, depth error, CLVD leakage; L0 includes the cross-code GF consistency oracle as its own scored task (agent must detect a corrupted GF store — negative-case discipline applied to synthetics engines).

**S4 `noise_chain` (extends `dvv`).** Generator: GF-store correlations with prescribed dv/v time series (known stretch) and known dispersion curves. Score: dv/v recovery RMS vs imposed signal, dispersion pick misfit, 1D model recovery (disba/evodcinv) vs truth within posterior. L3: seasonal noise-source variation confounds the dv/v (agent must not report source effects as velocity change — the classic field error, now scoreable).

**S5 `forward_sim` (Family 2, new).** Prompt→config: agent writes SPECFEM2D Par_file / SW4 command file for a specified scenario. Score: numerical regression of output seismograms vs reference run within tolerance; LOH.1 misfit (envelope/phase GOF); dispersion-criterion compliance (elements per wavelength — a config-correctness check that catches silent physics errors). L3: the prompt contains an infeasible request (dt too large, source above free surface); credit for refusing and explaining.

**S6 `fwi_2d` (Family 2, new).** Deepwave/SPECFEM2D checkerboard and Marmousi-crop recovery. Score: model misfit in target region, data misfit trajectory (did it actually converge or just iterate), cost telemetry (frugality: gradient evaluations spent).

**S7 `cycle_catalog` (Family 1/2 hybrid, later).** QDYN BP1-QD run → synthetic catalog → agent computes recurrence, b-value, coefficient-of-variation; L4 connects to pyCSEP scoring of a forecast against held-out cycles (the SEAS↔CSEP link from [02_connections_and_gaps.md](02_connections_and_gaps.md)).

**S8 `orchestration_twin` (Family 3, flagship).** The digital twin loop as an eval: given a simulated scenario recording (truth hidden), the orchestrator must plan and execute retrieve→pick→associate→locate→characterize→(optionally simulate to test a hypothesis)→report. Scored on: call-DAG vs reference (right steps, right dependencies, frugal fan-out — existing orchestration scorer), end-metric recovery (hypocenter/MT vs hidden truth), and cost. Difficulty graded by scene complexity and by whether the correct workflow requires the simulation branch.

## Split and contamination policy

Public split: generator code + a few worked seeds (development). Private split: held-out seeds + perturbation parameters, never published; regenerate quarterly. Cutoff-date fields (P1.2) apply to any retrieval-augmented task. Negative cases at every level ≥ L1, at fixed proportion, so precision is always measured. All suites emit Inspect-compatible logs and leaderboard rows with `openness`/`toolset` metadata (P1.3), keeping AstaBench comparability.

## Sequencing (aligned with the agent phases)

S1 with Phase A; S2+S3 with Phase B (codecs); S4 upgrade alongside NoiseMonitor; S5+S6 with Phase C; S7+S8 with Phase D. Each suite lands with: generator module, `scenarios.yaml` schema, deterministic scorer + tests, two public seeds, N private seeds, and a docs page following `docs/dataset_submission.md`.

## Sources

Key primary sources across the four research threads (full URL lists preserved in the research reports): obspy.org · pyrocko.org · seisbench (github.com/seisbench, v0.12) · noisepy.github.io · msnoise.org · dascore.org · github.com/AI4EPS (GaMMA/ADLoc/QuakeFlow) · github.com/yetinam/pyocto + Seismica associator benchmark · github.com/alomax/NonLinLoc · github.com/dttrugman/GrowClust3D.jl · specfem.org + github.com/PrincetonUniversity/SPECFEMPP · github.com/SeisSol/SeisSol + cheese2.eu · geodynamics.org (PyLith v5, SW4) · instaseis.net + ds.iris.edu/ds/products/syngine · docs.mondaic.com · github.com/adjtomo (SeisFlows/pyatoa) · github.com/uafgeotools/mtuq (GJI 2025) · eas.slu.edu/eqc (CPS) · github.com/ar4/deepwave · github.com/ydluo-c/qdyn · tandem (EarthArxiv 2025) · SCEC TPV + SEAS BP1–7 (strike.scec.org) · sismowine LOH.1 · earthscope.org/data/cloud (S3, TileDB) · scedc-pds/ncedc-pds AWS Open Data · GJI cloud seismology review (ggaf322) · cseptesting.org (pyCSEP/floatCSEP) · EarthquakeNPP (TMLR 2026) · TRACE (arXiv:2603.21152) · SPECFEM-MCP (arXiv:2512.14429, github.com/RenYukun1563/specfem-mcp) · earthquake-mcp-server (cyanheads) · AstaBench (allenai.org/asta/bench) · ScienceAgentBench · CORE-bench · SUPER · Fervo/Zanskar/Edison funding announcements (2025–2026) · gempa.de · imseismology.org · epa.gov/uic (Class VI).
