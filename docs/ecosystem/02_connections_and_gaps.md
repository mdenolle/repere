# Connections, gaps, and unwritten links

Part 2 of the ecosystem analysis. The first half maps connections that exist (explicit and implicit); the second half records connections the literature does not yet spell out — a research notebook for future investigation.

## Explicit workflow chains

Five chains carry most of the field's scientific output. Each is healthy at the nodes and brittle at the joints.

**Catalog chain**: FDSN/S3 data → SeisBench picker → GaMMA/PyOcto → NonLinLoc → HypoDD/GrowClust → magnitudes/QC. SeisBench→PyOcto is smooth (DataFrames); everything downstream is hand-written text-format converters. Every research group maintains a private, unversioned version of this pipeline. QuakeFlow and BPMF are the only integrations, each encoding one lab's choices.

**Noise chain**: NoisePy/MSNoise cross-correlations → dispersion picking (FTAN — no maintained standard tool) → disba/evodcinv/BayHunter inversion; or → MWCS/stretching dv/v monitoring. The middle step is notebook one-offs; the inversion layer is solo-maintained.

**Source chain**: waveforms → Green's functions (Syngine/Instaseis, fomosto, CPS, fk) → MTUQ or Grond or CAP. The most automatable chain in the field; already laptop-only thanks to precomputed GF stores (Syngine REST, Greens Mill downloads).

**Adjoint/FWI chain**: SPECFEM forward → pyflex windows → pyadjoint misfits → adjoint kernels → SeisFlows optimization. Automated in the loop, manual at setup (mesh, Par_file, compiled binaries remain the user's problem).

**Rupture/cycle chain**: Gmsh/SimModeler mesh → SeisSol dynamic rupture → ground motion; QDYN/tandem cycles → SEAS benchmark outputs; emerging coupling (cycle code sets initial stress for dynamic rupture).

## Implicit connections (present in the code, absent from the papers)

- **MTUQ's GF-client abstraction is a universal forward-model interface in embryo.** It already reads AxiSEM/Instaseis, FK, CPS, and SPECFEM3D Green's functions behind one API. Generalized, this is the "forward-model service" an agent needs: one call signature over every synthetics engine, 1D to 3D.
- **The pick DataFrame is a de facto standard nobody wrote down.** SeisBench, GaMMA, PyOcto, and ADLoc exchange picks as pandas DataFrames with informally agreed columns. There is no schema, no validation, no QuakeML mapping. Formalizing it (a "PickTable" schema) would connect the modern chain end-to-end and is a weekend of work with outsized payoff.
- **NonLinLoc grids are shared infrastructure.** QuakeMigrate and GrowClust3D.jl both consume NLLoc travel-time grids. NLLoc is quietly the travel-time engine of the ecosystem while being its least-funded component.
- **qseek already fuses the two hubs** (SeisBench pickers as characteristic functions inside Pyrocko migration), proving hub-bridging is feasible and valuable; no equivalent exists for the ObsPy↔Pyrocko data layer itself.
- **Cross-code agreement is an oracle.** Syngine, fomosto, and CPS synthetics for the same 1D model and moment tensor must agree to numerical tolerance. This is a free, deterministic self-verification an agent can run before trusting any downstream result — and it is not standard practice anywhere.

## Unwritten connections — future investigation notebook

These are links between tools or subfields that the literature has not spelled out. Each is a candidate research project, agent capability, or eval task.

1. **The digital twin loop (simulation → observation, closed).** SeisSol or SW4 scenario ruptures → synthetic continuous waveforms with realistic noise → fed through the full observational chain (pick/associate/locate/relocate/MT) → recovered catalog compared to the simulated truth. Nobody runs this loop end-to-end in the open. It would simultaneously (a) validate observational pipelines with known truth, (b) quantify what network geometry can and cannot resolve, and (c) generate unlimited contamination-free eval data. DT-GEO gestures at this; no open implementation exists.

2. **Cycle simulators as catalog generators for forecasting evals.** QDYN/tandem produce multi-millennium synthetic seismicity with physically consistent clustering. CSEP/pyCSEP has the most rigorous testing culture in seismology but tests against real (short, single-sample) catalogs. Connecting them — scoring ETAS and neural point-process forecasts against physics-generated catalogs where the true generative process is known — is an obvious, unmade link between the SEAS and CSEP communities.

3. **A forward operator from deformation modeling to dv/v.** MSNoise measures velocity changes; PyLith computes stress, strain, and pore-pressure evolution. No open software maps PyLith fields to predicted dv/v (via sensitivity kernels and stress/hydrology-velocity coupling). Building it would turn noise monitoring from correlation-watching into hypothesis testing, with immediate application to geothermal/CCS compliance.

4. **DAS moment tensors via strain GF stores.** fomosto can compute strain-rate Green's functions along an arbitrary fiber geometry; MTUQ/Grond can invert them. The pieces exist; the pipeline (fiber geometry → strain GF store → DAS-native source inversion) does not, and DAS channel mapping to pseudo-stations has no standard.

5. **Sim2real for seismic foundation models.** SeisLM/SeisCLIP-class models train on labeled real data (≤ a few TB). The modeling stack can generate unlimited labeled waveforms with exact arrival times, mechanisms, and structure. Nobody has published a seismic picker or foundation model pretrained on physics synthetics and finetuned on real data, though this is standard practice in speech and vision. The synthetic→real transfer gap itself is unmeasured for seismology.

6. **Noise correlations as Green's-function reconstructions, checked against GF stores.** Interferometry theory says a CCF converges to the inter-station Green's function; fomosto/Instaseis can compute that Green's function directly for a reference model. A closed-loop validator (NoisePy CCF vs GF-store prediction, phase and amplitude) would give the noise chain the verification layer the source chain already has, and would flag processing bugs (whitening, one-bit) that currently pass silently.

7. **Joint RF + dispersion + dv/v inversion with a shared parameterization.** BayHunter joins RF and dispersion; nothing joins them with time-dependent dv/v to invert for time-varying near-surface structure. Groundwater and geotechnical monitoring markets would pay for this (links to the water-table modeling agenda).

8. **The relocation glue as a product.** HypoDD's wrapper vacuum (hypoDDpy dead since ~2015) means the field's citation-standard relocator has no maintained modern interface. A tested ph2dt/dt.cc/dt.ct writer + runner + QuakeML round-trip is small, unglamorous, and would be adopted immediately — and it is precisely agent-shaped work.

9. **Uncertainty propagation across chain joints.** Pick uncertainty (SeisBench outputs it), association ambiguity, location posteriors (NLLoc computes them), and relocation bootstrap errors (GrowClust computes them) are each estimated and then thrown away at the next joint. No pipeline propagates uncertainty end-to-end from waveform to catalog to downstream inference (b-values, stress inversion). This is a methods paper and an agent differentiator in one.

10. **Squirrel + cloud object stores.** Pyrocko's Squirrel is the best local data-management abstraction; EarthScope's S3 + TileDB is the best remote store. They do not talk. A Squirrel backend for S3 miniSEED / TileDB arrays would define the missing cloud-native data layer while the community's zarr-vs-TileDB indecision persists.

11. **Exploration and earthquake FWI dialects never meet.** Devito/JUDI (SEG-Y, regular grids, AD gradients) and SeisFlows/SPECFEM (miniSEED, meshes, file-based adjoints) solve the same math with disjoint communities, formats, and vocabularies. A translation layer — or evals that pose the same inversion in both dialects — would expose which differences are physics and which are sociology.

12. **Agent prior art splits along exactly this fault line.** TRACE (Shanghai AI Lab + collaborators, 2026) is observational: raw waveforms → catalog → mechanistic interpretation, with an internal multi-level benchmark. SPECFEM-MCP (Harbin/PKU, Dec 2025) is modeling: SPECFEM as MCP tools, no evals. No system bridges observation and simulation — the loop in item 1 is also the open competitive frontier, and it maps directly onto Repère's orchestration family.

## Gap summary (ranked by value ÷ effort)

1. Pick-table schema + relocation glue (items above: pick DataFrame, HypoDD wrapper) — small effort, immediate adoption.
2. Cross-code consistency oracle (Syngine/fomosto/CPS) — small effort, foundation for all agent self-verification.
3. Digital twin loop as eval generator — medium effort, the core of the eval plan in [05_eval_design.md](05_eval_design.md).
4. Noise-chain validator (CCF vs GF store) and FTAN standardization — medium.
5. DAS source inversion, dv/v forward operator, sim2real pretraining — research-grade, publishable, longer horizon.
