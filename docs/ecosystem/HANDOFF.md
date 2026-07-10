# Handoff: agentic seismology project — context for Claude Code

Self-contained context dump (2026-07-09) so this work can continue in Claude Code inside the `frugalmind` repo without re-deriving anything. Read this first; details live in the sibling documents.

## What this project is

Build agents around the open-source seismology stack (observational + wavefield modeling), and grade them with multi-difficulty synthetic evaluations inside FrugalMind. Strategic frame: the agents are the demo, the eval suites are the moat. Full analysis in `docs/ecosystem/01–05` + `pitch_deck.html` (16 slides, self-contained HTML).

## File map

- `01_ecosystem_map.md` — tool inventory, interface taxonomy (70% clean Python APIs; ~8 legacy text formats are the valuable 30%), maintenance risk register, barrier ranking (meshing > config archaeology > HPC orchestration > format conversion > verification anxiety).
- `02_connections_and_gaps.md` — five workflow chains (catalog, noise, source, adjoint/FWI, rupture/cycle); implicit connections (MTUQ GF-client = embryo of a universal ForwardModelService; pick DataFrames = unstandardized de facto interchange; NLLoc grids = shared travel-time infrastructure; cross-code GF agreement = free verification oracle); twelve unwritten cross-field links (digital twin loop, SEAS→CSEP synthetic catalogs, PyLith→dv/v forward operator, DAS MT via strain GF stores, sim2real picker pretraining, CCF-vs-GF-store validator, joint RF+dispersion+dv/v, HypoDD glue revival, end-to-end uncertainty propagation, Squirrel-on-S3, Devito↔SPECFEM dialect bridge, TRACE/SPECFEM-MCP split).
- `03_market_analysis.md` — segments, incumbents, moats, funding, risks; extended 07-09 with tailings/reinsurance/water-ag/EO-context.
- `04_agent_plan.md` — 3 tiers (tools → operator agents → orchestrator), phases A–D, design rules.
- `05_eval_design.md` — 8 suites × L0–L4 ladder, 6 difficulty knobs, generator inventory, contamination policy.
- `pitch_deck.html` — colleague-facing pitch with all market numbers.

## FrugalMind state (as found)

v0.4.0, InspectAI substrate, pinned Docker sandbox, ReAct baseline with 3 tools. Three task families: (1) lit/multimodal RAG, (2) coding agents with numerical-regression scoring, (3) orchestration scored by call-DAG. Existing suites: `sta_lta` (reference; parametric `events.yaml`, negative-case discipline), `pipeline_regression`, `dvv` (codameter-backed), `gaia_data_downloader`, `lit_rag`, `orchestration`. Skills in `.github/skills/`: obspy-fdsn-fetch, seismic-plotting, seismic-report, seismo-data-agent, stalta-detection. Roadmap: P1 (splits/cutoff_date/openness metadata) partially on branches; P2.2 sandbox pinning next; P3 scales truth set to ~50 events. Non-negotiables: frugality-first (skill-lift, cost-Pareto, BudgetGuard), parametric truth set, negative-case discipline.

## Key findings (condensed)

**Ecosystem.** Observation is hub-and-spoke (ObsPy / Pyrocko / SeisBench); modeling is a barbell (pip-install source inversion ↔ HPC monoliths; thin middle = where Salvus monetizes). Chains are healthy at nodes, brittle at joints; HypoDD has had no maintained wrapper for a decade. Solo-maintainer keystones to vendor+pin: CPS, NonLinLoc, disba/evodcinv, BayHunter, rf, fk/CAP. Most agent-friendly configs: qseek (single Pydantic JSON), SW4 (one command file, no meshing). Zero-install ground truth: Syngine REST; laptop GF stores: pyrocko fomosto + Greens Mill.

**Prior art.** TRACE (arXiv:2603.21152) — observation-only multi-agent, internal unreleased benchmark. SPECFEM-MCP (arXiv:2512.14429, github.com/RenYukun1563/specfem-mcp) — simulation-only, no evals. Nobody bridges observation↔simulation; no public seismology-agent benchmark exists (AstaBench/ScienceAgentBench contain none). earthquake-mcp-server covers catalogs only; no MCP server exists for ObsPy/FDSN waveforms or SeisBench — cheapest win.

**User base (queried 2026-07-08).** ObsPy: 187k PyPI installs/mo, 1.3k stars, 116 contributors, ~3k citations. SeisBench: 30.6k/mo. Pyrocko 11.4k/mo. 31 FDSN data centers; 26k+ registered stations; AGU seismology 4,900+ members; 1.3 PB open waveforms on AWS (EarthScope+SCEDC+NCEDC, 47,354 stations).

**Market.** Today: geothermal (Fervo $462M E; TLP compliance), CCS/Class VI ($100–500k/yr analysis per site), mining (IMS ~210 systems), PSHA consulting ($200–400/hr), networks (gempa = open-core precedent; Mondaic ~$2M = license ceiling), DAS ($0.6–0.8B). Rising: offshore wind site investigation ~$1.5B/yr @11%; nuclear/SMR (127 designs, 51 in licensing, 85 siting discussions, PSHA mandatory per NRC 10 CFR 100.23 / IAEA SSG-9); SHM $3.6–4.5B @9–20%; data centers (~$600B capex 2026, hazard screening). Added 07-09: tailings (~8,500 facilities, GISTM + >$25T investor pressure, dv/v sees internal erosion InSAR/piezometers miss, geotech monitoring ~$5.1B), reinsurance/parametric ($18B→$39B; ShakeNet Parametric proves reinsurers pay for ground-truth shaking; $65.6B cat bonds; ShakeMap already trigger infrastructure), water/ag (SGMA 260+ GSAs, >$500M grants; dv/v groundwater = Denolle-lab chain, TRL 3–4, roadmap not TAM). EO context: seismic is the missing modality in EO foundation models (Prithvi/Clay/Major TOM ingest none); Illgraben ML debris-flow warning is the one operational climate-hazard proof point; NISAR 85 TB/day. Aggregate: ~$12–15B/yr analysis layer growing ~10%/yr. Business template: FutureHouse→Edison (nonprofit + spinout) × gempa (open-core support). Funding: DOE (GTO/FECM/SBIR) strongest; NSF NAIRR/CSSI; EU DT-GEO/ChEESE-2P/DestinE; Schmidt/InnerSpace philanthropy.

## The plan (what to build, in order)

**Phase A (now, ~6 wk).** (1) `PickTable` schema — formalize the pick-DataFrame interchange (columns, dtypes, QuakeML round-trip, validation); (2) tool wraps for ObsPy FDSN/S3, SeisBench, PyOcto/GaMMA, TauP, Syngine/Instaseis, fomosto; (3) DataScout + CatalogBuilder operator agents on the existing ReAct baseline; (4) `pick_associate_locate` suite: fomosto-generated regional scenes in a `scenarios.yaml` (generalizing `events.yaml`), L0–L4, scorers = pick residual distribution, association precision/recall, hypocenter km error, uncertainty calibration; negative cases from L1; public seeds + private seeds.

**Phase B (~wk 6–14).** NLLoc/HypoDD/GrowClust codecs (writers/parsers + run harness + round-trip property tests) → release as standalone "relocation glue" package (community adoption play); SourceEstimator (MTUQ/Grond) with cross-code GF-consistency oracle; `relocate` + `source_mt` suites; NoiseMonitor upgrade of `dvv` with imposed-stretch ground truth.

**Phase C (~wk 14–26).** SimulationRunner for SPECFEM2D/SW4/Deepwave (config generation + dry-run validators + LOH.1/analytic self-checks); `forward_sim` + `fwi_2d` suites; assess SPECFEM-MCP interop instead of duplicating.

**Phase D (mo 6–12).** Orchestrator + digital-twin loop (simulate hidden scenario → agent recovers it end-to-end → deterministic scoring) as `orchestration_twin`; first external pilot (geothermal compliance report), human sign-off built in.

**Design rules.** Every operator self-verifies against a deterministic oracle before returning. Small models for extraction/translation, frontier only for planning (FrugalRouter). Vendor+pin fragile deps with synthetic regression tests. Provenance on every artifact. Private seeds regenerated quarterly; Inspect-compatible logs; AstaBench-comparable `openness`/`toolset` metadata.

## Eval difficulty knobs (shared across suites)

Signal (SNR, magnitude, noise realism) · scene complexity (single → overlapping → swarms; negative cases first-class) · network (dense → sparse → one-sided; metadata faults) · model mismatch (truth in model A, tools given model B) · tool tier (Python API → CLI/config → legacy codec → HPC) · autonomy (full spec → underspecified → adversarial). L0 = one tool, clean, specified; L4 = underspecified goal, orchestration scored by call-DAG.

## Open questions / decisions pending

- `scenarios.yaml` schema design (superset of `events.yaml`? separate per-suite?) — decide during Phase A item 1.
- MCP servers vs Inspect tools vs both: recommend both from one wrapper layer (Inspect tools for evals, MCP for external use).
- Whether to contribute `pick_associate_locate` upstream to `inspect_evals` (roadmap P3.1 pattern).
- DAS suites deferred until DASCore API stabilizes (pre-1.0).
- Pilot targeting: geothermal operator vs regional network first — market doc argues geothermal; network is lower-friction for data.

## Immediate next actions in Claude Code

1. Draft `scenarios.yaml` schema + generator module skeleton under `src/frugalmind_suites/pick_associate_locate/`.
2. Implement PickTable (pydantic/pandera) with QuakeML round-trip tests.
3. Wrap fomosto scene generation (pin a Greens Mill store; laptop-runnable; cache in `tests/fixtures/`).
4. Scorers: association P/R vs known membership; hypocenter error; calibration (posterior coverage).
5. Wire into Inspect `@task` following `sta_lta/inspect_tasks.py` conventions; add drift tests per repo pattern.

## Verified anchors (checked directly)

TRACE arXiv:2603.21152 · SPECFEM-MCP arXiv:2512.14429 + github.com/RenYukun1563/specfem-mcp · GitHub/PyPI/citation numbers queried 2026-07-08 via pypistats/shields/Semantic Scholar. Vendor-report figures (SHM, DAS, parametric, offshore-wind geotech) are ranges, flagged as analyst estimates in `03_market_analysis.md`. The "30,000 tailings dams" figure circulating in vendor decks is unsupported — use ~8,500 (~1,900 disclosed). No public per-plant PSHA cost exists; do not invent one.
