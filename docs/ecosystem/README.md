# Ecosystem analysis: open-source seismology as agent substrate

Market and technical deep dive (July 2026) into the open-source seismology software ecosystem, done as groundwork for building agents around high-barrier tools and extending Repère's evaluation suites. Five documents:

1. [Ecosystem map](01_ecosystem_map.md) — tool inventory, interface taxonomy, maintenance risk register, barriers to entry.
2. [Connections and gaps](02_connections_and_gaps.md) — explicit workflow chains, implicit connections present in code but absent from papers, and a notebook of twelve unwritten cross-field links for future investigation.
3. [Market analysis](03_market_analysis.md) — customer segments, incumbents, startup analogies, moats, funding, risks.
4. [Agent build plan](04_agent_plan.md) — three-tier architecture (tools → operator agents → orchestrator), four phases, design rules.
5. [Eval design](05_eval_design.md) — eight multi-difficulty synthetic suites (L0–L4) mapped to Repère's task families, with the modeling stack as the eval generator for the observational stack.

## Findings in brief

The ecosystem is hub-and-spoke on the observational side (ObsPy, Pyrocko, SeisBench) and barbell-shaped on the modeling side: friction-free Python source inversion at one end, HPC monoliths at the other, and a thin middle where Salvus monetizes. Scientific value flows through five chains whose nodes are healthy and whose joints are hand-written glue; the relocation joint (HypoDD wrappers) has been abandoned for a decade while remaining citation-standard. About 70% of the stack wraps as agent tools at near zero cost; the valuable remainder is roughly eight legacy text formats plus config generation for meshed HPC codes.

Prior art splits along the observation/simulation fault line — TRACE (observational multi-agent, internal benchmark, unreleased) and SPECFEM-MCP (simulation tools, no evals) — and no one bridges the loop. No public benchmark grades agent competence in waveform seismology; the general science-agent benchmarks (AstaBench, ScienceAgentBench) contain zero seismology. The defensible position is therefore not tool wrapping but the evaluation layer: generator-backed, difficulty-laddered, contamination-free synthetic suites with private seeds — which is Repère's existing design generalized from STA/LTA to the whole field.

Highest-momentum paying segments: geothermal induced-seismicity compliance, CCS/Class VI monitoring, mining, PSHA consulting, national networks. The working business template is FutureHouse→Edison (nonprofit credibility + commercial spinout) combined with gempa-style open-core support — not per-seat SaaS.

Provenance: synthesized from four parallel research threads (observational stack, modeling stack, data/ML/agent infrastructure, market) run 2026-07-08; primary sources listed per document.
