# The open-source seismology ecosystem: structure and health (July 2026)

Companion documents: [connections and gaps](02_connections_and_gaps.md) · [market analysis](03_market_analysis.md) · [agent build plan](04_agent_plan.md) · [eval design](05_eval_design.md).

## Shape of the ecosystem

Two structural facts organize everything else.

**The observational side is hub-and-spoke.** ObsPy is the hub: `Stream/Trace/Inventory/Catalog` objects and the FDSN format triad (miniSEED, StationXML, QuakeML) are the interchange layer almost every tool imports. Pyrocko (GFZ) is a second, Europe-centric hub with its own objects, the Squirrel data layer, and the fomosto Green's-function store system; interop with ObsPy is a thin adapter, so the two ecosystems mostly duplicate each other. SeisBench is the third hub, for ML: one `model.classify(stream)` API over PhaseNet, EQTransformer, PickBlue, DeepDenoiser, and (since v0.12) DAS models, plus the benchmark datasets (STEAD, INSTANCE, ETHZ, NEIC, CEED).

**The modeling side is a barbell.** One end is friction-free Python source inversion: FDSN waveforms → Syngine/Instaseis precomputed Green's functions → MTUQ or Grond, all pip-installable, laptop-scale, minutes to a moment tensor with uncertainty. The other end is HPC monoliths — SPECFEM3D, SeisSol, PyLith at scale — where meshing, parameter-file archaeology, and job orchestration take weeks to learn. The middle (automated meshing, config generation, workflow orchestration) is thin: SeisFlows/adjTomo covers the FWI loop, SPECFEM++ is modernizing the config surface, and the one complete solution — Salvus — is closed source and is the moat Mondaic monetizes.

## Layer-by-layer inventory

| Layer | Tools | Interface | Health |
|---|---|---|---|
| Data access | ObsPy FDSN clients, Pyrocko Squirrel, obspyDMT (dead), ObsPlus banks, EarthScope S3, SCEDC/NCEDC S3 (anonymous) | Python + REST + S3 | Hubs healthy; glue stale |
| Picking | SeisBench zoo (PhaseNet, EQT, PickBlue, OBSTransformer), ELEP ensembles | Python | Excellent; bus factor 2–3 |
| Association | PyOcto, GaMMA, REAL | Python | Active, solo-PI |
| Location | NonLinLoc, HypoInverse, ADLoc | C + control files / Python | NLLoc "always BETA", no funding |
| Relocation | HypoDD (Fortran tarball), GrowClust3D.jl | Fixed-format text files | **Wrapper vacuum** — hypoDDpy dead a decade |
| Detection (other) | EQcorrscan, FMF, QuakeMigrate, qseek, BPMF | Python / JSON config | Good; qseek most agent-friendly config in the field |
| Ambient noise | NoisePy (cloud refactor, SCOPED), MSNoise (2.0 in progress), SeisNoise.jl | Python / CLI+DB | Active; API churn |
| Dispersion + 1D inversion | disba, pysurf96, evodcinv, BayHunter | Python | **Thin ice**: solo-maintained, one numba bump from breaking |
| Receiver functions | rf (Eulenfeld) | Python | Solo, low intensity |
| DAS | DASCore/DASDAE, DASstore, SeisBench-DAS | Python | Active, pre-1.0 |
| Forward modeling 1D/GF | Syngine (REST), Instaseis, fomosto+Greens Mill, CPS, fk/PyFK | REST / Python / Fortran | Syngine zero-friction; **CPS at succession risk** (Herrmann emeritus) |
| Forward modeling 3D | SPECFEM2D/3D/GLOBE, SPECFEM++, SW4, OpenSWPC, AxiSEM3D | Par_file / command file / YAML | CIG/ChEESE backed; SPECFEM++ is the successor bet |
| Dynamic rupture | SeisSol | parameters.par + easi + tet mesh | Very healthy (LMU/TUM, ChEESE-2P) |
| Quasi-static / cycles | PyLith v5, QDYN, tandem | .cfg / Lua / Python | PyLith healthy; cycle codes research-grade |
| FWI / adjoint | SeisFlows (adjTomo), pyflex/pyadjoint/pyatoa, Deepwave, Devito+JUDI | YAML / PyTorch | adjTomo active; Deepwave the classroom default |
| Source inversion | MTUQ, Grond, CAP/gCAP, wvfgrd96 | Python / config | MTUQ+Grond active; CAP frozen-but-functional |
| Real-time ops | SeisComP 7 (GFZ+gempa), Earthworm 8 | Config forest | Healthy; gempa is the field's open-core business |
| Scale layer | MsPASS (MongoDB+Dask), QuakeFlow (k8s) | Containers | Powerful, adoption-limited by complexity |

## Interface taxonomy (what an agent can wrap, at what cost)

Roughly 70% of the observational stack has clean Python APIs and can be wrapped as agent tools for near zero cost: ObsPy, SeisBench, PyOcto, GaMMA, EQcorrscan, DASCore, disba/evodcinv, rf, NoisePy, MTUQ, Instaseis, Pyrocko. The high-value remaining 30% is legacy interfaces requiring format codecs plus a run harness: NonLinLoc keyword control files, HypoDD fixed-format text (dt.ct/dt.cc/ph2dt), GrowClust inputs, CPS conventions, SPECFEM Par_file + multi-executable sequence, SeisSol parameters+easi+mesh coherence, SeisComP module configs. That is a bounded set of roughly six to eight text formats — tedious for a human, exactly the kind of deterministic, testable translation work agents and round-trip tests handle well.

Config-file style predicts agent-readiness: qseek (one Pydantic JSON) and SW4 (one free-format command file, no meshing step) are the easiest serious tools to drive programmatically; SPECFEM3D (Par_file cross-consistency with mesh partitioning, errors surfacing as MPI crashes) and SeisComP (module forest) are the hardest.

## Maintenance risk register

The ecosystem's health is bimodal. Consortium-backed hubs are safe: CIG (SPECFEM, PyLith, SW4), ChEESE-2P (SeisSol), GFZ (Pyrocko, SeisBench, SeisComP), EarthScope (Syngine, S3 data), NSF/SCOPED (NoisePy, MsPASS), adjTomo. Single-PI keystones are load-bearing and fragile: CPS (40 years of Fortran, emeritus author), NonLinLoc (unfunded), HypoDD glue (abandoned), disba/evodcinv (solo, feature-frozen), BayHunter (dormant), rf (solo), fk/CAP (tarball distribution). Several dead tools are still cited in tutorials (hypoDDpy, obspyDMT, covseisnet), which costs every novice days. Any agent product built on this stack needs a policy for the fragile layer: vendor the code, pin it, test it against synthetics, and be ready to maintain forks.

## Barriers to entry, ranked by user pain

1. Meshing (SPECFEM3D hex meshes, SeisSol fault-conforming tets; CUBIT is commercial). Tools without a meshing step (SW4, OpenSWPC, Deepwave, AxiSEM3D) win adoption for this reason alone; Salvus's auto-meshing is its commercial moat.
2. Parameter-file cross-consistency (Par_file vs mesh vs NPROC; SeisSol easi vs mesh tags). Errors are delayed and cryptic.
3. HPC orchestration: multi-executable sequences, Slurm, restarts; inversions multiply this by 10²–10⁴ runs.
4. Legacy format conversion: CMTSOLUTION vs NDK vs pyrocko MT sign/unit conventions; SAC vs ASDF vs NetCDF; GF-store naming.
5. Verification anxiety: users cannot tell whether a wrong-looking synthetic is physics, mesh dispersion, units, or a flipped component. Cross-code agreement (Syngine vs fomosto vs CPS on the same 1D model) is a cheap oracle nobody has productized.
6. Parameter tuning in the observational chain (GaMMA hyperparameters, NLLoc grids, EQcorrscan memory) plus knowing which of several overlapping tools to use at all.

Full research notes with per-tool sources are preserved in the reports that produced this document; primary URLs are in [05_eval_design.md](05_eval_design.md#sources) and inline above.
