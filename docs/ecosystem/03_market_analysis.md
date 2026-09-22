# Market analysis: agents for seismology as a startup thesis

Part 3 of the ecosystem analysis. Framing: who would pay for agent-driven seismic analysis, who already monetizes this stack, and where the defensible position is.

## Who pays today

**Geothermal** is the highest-momentum segment. Fervo closed a $462M Series E (Dec 2025) plus $421M project financing; Zanskar raised $115M Series C (Jan 2026) explicitly on AI-driven exploration. Every EGS operator carries a traffic-light-protocol obligation for induced seismicity, which means recurring, compliance-driven demand for detection, location, magnitude, b-value, and Mmax analysis — repetitive expert work that is chronically analyst-limited. Project InnerSpace has a stated ~$6M gap for AI integration into GeoMap.

**CCS / Class VI** is a compliance annuity: EPA permits require seismic monitoring before, during, and decades after injection. Per site: roughly $0.5–3M array install plus $100–500K/yr analysis. The analysis line is where agents substitute. Incumbents selling it: Nanometrics (Athena platform + human analysts as a managed service), MicroSeismic, ESG, Silixa.

**Mining**: Institute of Mine Seismology alone runs ~210 systems in 34 countries; rockburst analysis is safety-regulated and mine seismologists are scarce. **Engineering/PSHA consulting** (Lettis, Fugro, boutiques) bills $200–400/hr for codified workflows — deaggregation, GMPE logic trees, site response, SPECFEM/SW4-class ground-motion runs — driven now by data-center siting. **Defense/treaty monitoring** (AFTAC ~1,000 staff; CTBTO analysts producing reviewed bulletins in 2 days) is the canonical expensive-experts-doing-repetitive-review story, with long sales cycles. **National networks/EEW** have modest budgets but grant-funded procurement and the highest credibility value; gempa's client list proves agencies pay for support around an open core. **DAS** (~$0.7–1B market, heading to $2–3B) is hardware vendors drowning in TB/day with almost no trained analysts — an interpretation layer the instrument makers do not own. Insurance cat modeling is rich but consolidated (Moody's RMS, Verisk); better served by selling them catalogs and site studies than agents.

## Who monetizes open-source seismology now

gempa GmbH is the existence proof: SeisComP is open, gempa sells extensions, training, 24/7 support, and turnkey monitoring centers to national agencies. Mondaic (Salvus) licenses closed physics with superb UX at roughly $2M revenue — the ceiling of pure tool licensing. Nanometrics already sells analysis-as-a-service with humans in the loop; an agent stack attacks their analyst cost line. Nobody sells support or productization of the Python research stack (ObsPy/SeisBench/HypoDD/NoisePy) the way gempa does for SeisComP. That slot is open.

## Startup analogies

FutureHouse → Edison Scientific ($70M seed at $250M, Dec 2025) is the closest template: philanthropy-funded nonprofit builds agents and credibility, for-profit spinout sells to industry. Zanskar and KoBold ($3B+ valuation) show earth-science AI captures the most value as an asset developer, keeping the AI internal — they are customers or exits for tooling, not competitors. Earthmover (Zarr/Icechunk, $7.2M seed) is the infra-layer analog and a natural partner for DAS data. Agentic-AI startups raised $2.66B across 44 rounds in Jan–Apr 2026; vertical agents for expensive experts (Harvey in legal) are the proven pattern. Business models that work here, in order: managed monitoring service priced per site ($10–40K/mo), per-analysis compliance deliverables, open-core + support (gempa pattern), license + consulting (Mondaic pattern). Per-seat SaaS to academics does not work.

## Segment ranking (willingness-to-pay × agent fit)

1. Geothermal operators — funded, regulated, Python-native, analyst-starved.
2. CCS/Class VI holders and their consultants — mandated multi-decade monitoring.
3. Mining — normalized per-mine subscriptions, safety-driven.
4. PSHA/engineering consultancies — agents as a margin machine on codified workflows.
5. National networks / treaty monitoring — slow money, strategic credibility, grant-fundable.

## Where the moat is

Tool wrapping is not defensible: SPECFEM-MCP shipped in months, and frontier-model coding keeps commoditizing wrappers. The defensible assets are:

- **Eval suites.** Regulators, DOE reviewers, and insurers need demonstrated missed-event rates, location error, magnitude bias against golden catalogs. A published, versioned benchmark harness for seismic agent tasks becomes the standard others must beat. This is Repère's position, and no one else holds it — TRACE's benchmark is internal to one paper, SPECFEM-MCP shipped no evals.
- **Golden datasets + synthetic generators** at controlled difficulty (the contamination-free eval data that classic sequences, memorized by every LLM, cannot provide).
- **Compliance-artifact templates with provenance/audit trails** (regulator-ready TLP and Class VI reports) — switching costs.
- **Community credibility**: maintainership, open science, a nonprofit research arm attracting data-sharing agreements philanthropic funders will back (Schmidt AI-in-science, Moore lineage).

## Additional verticals (added 2026-07-09)

**Tailings dams.** ~8,500 facilities globally, ~1,900 disclosed in the Global Tailings Portal; lifetime failure rate ~1.2%. Brumadinho cost Vale $7B, Samarco settled at ~$30B (Oct 2024). GISTM — backed by an investor initiative holding >$25T AUM — mandates monitoring; only 67% of 836 ICMM facilities conform (Aug 2025), and the Global Tailings Management Institute (Jan 2025) now runs third-party audits. Insurance capacity collapsed post-Brumadinho (limits cut ~1/3, premiums doubled). The seismic edge: dv/v ambient-noise monitoring detects internal erosion that InSAR/GNSS (surface) and piezometers (point) miss — Olivier et al. 2017 caught rain-driven seepage on an operating dam that conventional instruments missed; IMS and Silixa (DamPulse DAS) already sell passive-seismic dam products. Geotechnical instrumentation and monitoring market: ~$5.1B (2026), ~9.6%/yr.

**Reinsurance / parametric.** Six consecutive years >$100B insured cat losses; $790B reinsurance capital; $65.6B cat bonds outstanding (H1 2026). Parametric insurance ~$18B → ~$39B by 2030. ShakeMap/PAGER are de facto parametric trigger infrastructure; Liberty Mutual Re + Safehub's ShakeNet Parametric (2024, extended to Mexico 2026) markets ground-truth shaking data as the basis-risk differentiator — direct proof reinsurers pay for better ground-motion analysis. Descartes Underwriting: >$200M GWP, ~30%/yr growth. Vs30/site amplification remains a flagged dominant uncertainty in loss models; landslide and liquefaction are non-modeled perils.

**Water / agriculture (roadmap-stage, honest).** Precision ag $11–12B → $21–24B by 2030; soil-moisture sensing only ~$0.3–0.7B. SGMA created 260+ California groundwater agencies with >$500M in DWR grants (Round 2 oversubscribed 4×). Seismically derived groundwater/soil moisture (Clements & Denolle 2018 → Mao et al. 2022 Nat. Comms → Mao et al. 2025 Science; DAS dark-fiber aquifer monitoring) is TRL 3–4 with zero commercial products — present as a research thrust the agent + eval infrastructure de-risks, not as TAM. Nearest buyers: GSAs/water districts via grant-funded pilots, then utilities and ag lenders (Growers Edge bought AQUAOSO in Dec 2024).

**Broader EO/geophysics context.** Seismology's cross-domain claims: (1) interior-state sensing where InSAR/GNSS see only the surface (dam seepage, depth-resolved groundwater, pre-failure landslide softening — Mainsant 2012); (2) one operational climate-hazard proof point (Illgraben ML debris-flow detection, +20 min–1.5 hr warning) with everything else stuck at retrospective papers — an agents-and-evals gap, not a physics gap; (3) seismic is the missing modality in the EO stack: NISAR ships 85 TB/day, DestinE has >€315M, and Prithvi/Clay/Major TOM ingest no seismic waveforms — the seismic+EO fusion slot and multimodal foundation model are uncontested. Adjacent open-source ecosystems where the same wrap-and-evaluate playbook applies: InSAR (ISCE/MintPy/LiCSBAS — the only stack with ObsPy-level penetration), SimPEG/pyGIMLi (hydrogeophysics), OpenSees (geotechnical), Fatiando (potential fields). Climate finance passed $2T in 2024; adaptation ~$65B/yr.

## Non-dilutive funding map

DOE is the strongest fit (GTO/FORGE EGS FOAs, FECM storage partnerships, SBIR topics in geothermal MMV and CCS monitoring). NSF is under FY2026 pressure but NAIRR survives with bipartisan support and is the natural home for agentic-AI + geoscience cyberinfrastructure; CSSI/Geoinformatics continue. USGS external grants ($4–7M/yr) are small but reputationally valuable. EU money (DT-GEO follow-ons, ChEESE-2P, Geo-INQUIRE, Destination Earth) funds exactly the containerized pre-agentic plumbing agents sit on and hedges US volatility.

## Risks

Fragmented TAM outside O&G (each monitoring niche is $10s–100s of M, so venture scale requires managed services or value capture, not licenses). Incumbent bundling (Nanometrics/ESG/IMS can bolt LLMs onto existing contracts). Wrapper commoditization (moat must live in evals, data, compliance trust). Liability: missed induced events carry legal exposure; human sign-off should be designed as the product, not a stopgap. Federal funding volatility. Proprietary data friction: the best commercial data (frac microseismic, mine catalogs) is closed; open data (FORGE, TexNet, EarthScope) only partially matches paying use cases. Founder conflict-of-interest needs the FutureHouse/Edison structural separation from day one.

Sources for every claim above are in the market research report backing this document; headline items: Fervo Series E (fervoenergy.com), Zanskar Series C (TechCrunch 2026-01-21), Edison Scientific seed (Dec 2025), gempa (gempa.de/products/seiscompro), Mondaic revenue estimate (RocketReach), IMS (imseismology.org), EPA Class VI (epa.gov/uic), DAS market (SNS Insider/GM Insights 2026), agentic funding (newmarketpitch.com 2026), SPECFEM-MCP (arXiv:2512.14429), TRACE (arXiv:2603.21152).
