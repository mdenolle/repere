# Agent build plan

Part 4 of the ecosystem analysis. Design principle: every agent ships with its eval suite, because the evals are the moat and the agent is the demo. Each phase produces both a capability and a FrugalMind suite (see [05_eval_design.md](05_eval_design.md)).

## Architecture: three tiers

**Tier 1 — Tools (deterministic, no LLM).** Typed wrappers exposing each ecosystem capability as a callable with validated inputs/outputs. Implementation: Python packages + MCP servers + FrugalMind/Inspect tools. Two classes of work:

- Cheap wraps (Python APIs already exist): ObsPy data access (FDSN + S3), SeisBench pick/classify, PyOcto/GaMMA associate, MTUQ/Grond invert, Instaseis/Syngine/fomosto synthetics, disba forward dispersion, NoisePy/MSNoise steps, DASCore, Deepwave FWI, TauP travel times.
- Codec wraps (the 30% that pays): writers/parsers + run harnesses for NonLinLoc control files and grids, HypoDD (ph2dt, dt.ct/dt.cc, station.dat), GrowClust3D inputs, CPS/fk GF conventions, SPECFEM Par_file + CMTSOLUTION + STATIONS + executable sequencing, SW4 command files, SeisSol parameters+easi. Every codec gets round-trip property tests and cross-code consistency checks. This layer alone is a community contribution (it fixes the wrapper vacuum) and a data-gathering instrument (telemetry on where agents fail reveals where humans fail).

Also in tier 1: a **PickTable schema** (the pandas-DataFrame de facto standard, formalized with QuakeML round-trip) and a **ForwardModelService** interface generalizing MTUQ's GF-client abstraction — one signature over Syngine/fomosto/CPS/SPECFEM synthetics.

**Tier 2 — Operator agents (one chain each).** Small ReAct agents (FrugalMind already has the baseline) that own one workflow chain, hold its domain skill file, choose parameters, run QC, and self-verify against deterministic checks:

1. **DataScout** — event/station/waveform retrieval, gap/response QC, format debugging. (Extends the existing `seismo-data-agent` / `gaia_data_downloader` work.)
2. **CatalogBuilder** — pick → associate → locate → relocate → magnitudes, with uncertainty carried across joints. The highest-demand agent (network ops, geothermal/CCS compliance, mining).
3. **SourceEstimator** — GF acquisition → MTUQ/Grond moment tensor with UQ; self-verifies via cross-code GF agreement before inverting.
4. **NoiseMonitor** — correlation → dv/v (and dispersion), with the CCF-vs-GF-store validator as its sanity check. Backs the existing `dvv` suite.
5. **SimulationRunner** — config generation, dry-run validation, resolution/dispersion checks, job orchestration for SPECFEM2D/SW4/Deepwave (laptop tier) then SPECFEM3D/SeisSol (HPC tier). Meshing avoidance strategy: prefer no-mesh codes first; treat meshed codes as an escalation.
6. **StructureInverter** — dispersion/RF/joint 1D inversion (disba/evodcinv/BayHunter), later 2D FWI via Deepwave and SeisFlows.

**Tier 3 — Orchestrator.** The scientist agent: given a question ("did injection at X trigger the M4.2?", "what does this sequence's geometry imply?"), it plans a DAG across operator agents, routes each step by cost (FrugalRouter), and closes the observation↔simulation loop — the frontier neither TRACE (observation-only) nor SPECFEM-MCP (simulation-only) occupies. This is FrugalMind Family 3 made real.

## Phasing

**Phase A (weeks 1–6): cheap wraps + two operators.** Ship the Python-API tool layer, PickTable schema, DataScout and CatalogBuilder against synthetic data only. Deliverable: end-to-end synthetic catalog recovery demo + `pick_associate_locate` eval suite.

**Phase B (weeks 6–14): codecs + source/noise operators.** NLLoc/HypoDD/GrowClust codecs with round-trip tests; SourceEstimator with the cross-code oracle; NoiseMonitor upgrade of the dvv suite. Deliverable: relocation glue release (community adoption play) + `source_mt` and `noise_gf` suites.

**Phase C (weeks 14–26): simulation.** SimulationRunner for SPECFEM2D/SW4/Deepwave, config-generation skills with dry-run validators, LOH.1 and analytic-solution self-checks. Deliverable: `forward_sim` and `fwi_2d` suites; SPECFEM-MCP interop assessed rather than duplicated.

**Phase D (months 6–12): orchestration + digital twin loop.** The closed loop (simulate scenario → synthetic network recording → CatalogBuilder → compare to truth) as both flagship demo and eval generator; orchestration suite expansion; first external pilot (geothermal compliance report or a network's analyst-assist), human sign-off built in.

## Design rules

- Self-verification before delivery: every operator runs a deterministic oracle (cross-code GF agreement, travel-time residual sanity, unit/polarity checks) before returning results; failures route to escalation, not silent output.
- Frugality is architectural: parameter extraction, format translation, and report drafting go to small models; frontier models only for planning and anomaly interpretation. The eval suites measure the floor each model clears (FrugalMind's core thesis).
- Fragile-dependency policy: vendor and pin the solo-maintainer layer (disba, NLLoc, HypoDD, CPS); maintain forks with synthetic regression tests.
- Provenance everywhere: every artifact carries the tool versions, parameters, and data windows that produced it (compliance-report readiness from day one; MsPASS's provenance model is the reference).
- Human-in-the-loop is the product for compliance outputs; autonomy is for the synthetic/QC tiers.
