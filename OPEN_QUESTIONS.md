# Open questions for Repère-RCA

Everything the design needed from Marine and could not resolve from the
repositories. Each question says what was assumed in the meantime, so the
skeleton runs, and what changes if the answer differs. Q1 to Q8 gate the
next steps in DESIGN.md §8.

## Q1. Naming

The lab's GAIA and the GAIA benchmark (Mialon et al., 2023) collide, and the
private repo `mdenolle/gaia-eval` collides with benchmark tooling names.
Proposal: always "GAIA HazLab" in prose; "Repère-RCA" for this suite;
rename `gaia-eval` to `hazeval` before anything public references it.
Assumed: the proposal. Alternative: keep "GAIA" and add a footnote at first
mention.

## Q2. Whiteboard item under 1d: "data: nc ... python" (UNKNOWN)

Not filled in. Two readings: (a) inputs may be NetCDF (`.nc`) as well as
MiniSEED, which would add `kind: netcdf` inputs and an xarray-capable
sandbox image; (b) it names the deliverable format ("return a .nc file from
Python"). The schema already allows `kind: netcdf`; no seed uses it.

## Q3. Whiteboard row label for the model sweep (UNKNOWN)

Treated as the model axis (Claude, OpenAI, Gemini, Olmo, Qwen, Kimi,
Mistral). The price map has one provider block per name; only the Anthropic
block has rates. Needed: for each provider, the exact model id(s) to sweep,
whether local (0 USD, digest-pinned) or hosted, and the reasoning-effort
setting to hold fixed.

## Q4. Corpus source of truth for the lit-review agent

aRCADA's index is a Zotero export with year-only dates and no rebuild path
outside the authors' machine. Proposal: rebuild from the same DOIs via
OpenAlex or Crossref with full publication dates and an `indexed_at`
snapshot date, and treat the DOI list (not Zotero) as the source of truth.
Assumed: aRCADA `papers.json` at commit 14294bc as snapshot v0. Needed: who
owns the DOI list, and whether the 10 PDF-only documents without DOIs stay
in the corpus.

## Q5. Licences for redistributed data

aRCADA's catalog and paper index carry no data licence (the code is MIT);
the 18 full-text PDFs' open-access status is unverified; OOI data-use and
EarthScope terms are cited nowhere yet; instrument photos have no source.
Assumed: nothing is redistributed; the fetch script pulls by commit and
hash. Needed: permission from the aRCADA authors to include catalog-derived
records in a public artifact, the exact OOI data-use statement to cite, and
the photo gallery terms.

## Q6. Prices

Two written sources disagree on Opus 4.6 (15/75 USD per million in
`config/models.yaml` dated 2026-05-08; 5/25 in a table dated 2026-06-24).
Every card in `pricing/prices.yaml` is `verified: false`. Needed: a person to
verify each rate against the provider page on a stated date and set
`verified_by`. Also: the cost convention for local models (0 USD, or an
energy or hardware-floor axis per repere issues #39 to #44).

## Q7. The T1 reference and tolerance

chronfix's delivered series is a software estimate against HYS12, validated
closed-loop, with stated sigma 0.08 to 0.17 s (DESIGN.md §3.1c). Needed:
(a) is HYS12 an acceptable timing reference, or should the reference be
strengthened (HYSB1 cross-check at 0.1 to 0.3 Hz; teleseismic P arrivals
against TauP predictions; a fresh chronos run on a post-2026-05 window held
privately); (b) the scoring tolerance (placeholder 0.5 s); (c) whether the
public T1 item may use a window covered by the public chronfix file
(answerable by lookup) or only the private split may. Also: does chronos
exist as code anywhere, and can its documented recipe be re-run for other
stations (AXCC1, AXBA1) to widen the T1 pool?

## Q8. GEPA split policy

GEPA needs train and validation sets it may see and a test set it never
sees; gold flows into the reflection prompt, so test answers must differ in
their values, not just their wording. Options: add `gepa_train` and
`gepa_val` values to `holdout.split`, or keep a separate manifest that
assigns validation records to GEPA roles. Assumed: no GEPA use until the
replay track and 30 verified records per family exist.

## Q9. Record-mode credentials and rate limits

Record-mode runs need an OOI API username and token and hit EarthScope for
data. Needed: whose credentials, what daily volume is acceptable, and
whether a UW-internal mirror of OOI seismic data can serve as the recording
source instead.

## Q10. Where the hidden split lives

repere documents two modes (derive from a secret; gated host with pinned
revision). RCA private items are real data and cassettes, so Mode B.
Needed: the host (gated HuggingFace dataset as planned in P3.3, or a UW
share) and who holds the token.

## Q11. Judges and raters

T4 items need two raters and a calibration set before any judge score is
reported. Needed: who the raters are (RCA engineer, PI, student), the
agreement threshold (0.6 kappa assumed, from the group's gaia-eval labelling
guide), and the judge model to pin.

## Q12. Scope of the sensor knowledge base

Proposed sources in DESIGN.md §3.3 include OOI M2M annotations and
calibration endpoints (token required) and instrument photos. Needed: which
of these are in scope for the first version, and whether the sensor agent
is aRCADA itself or a new agent.

## Q13. Harbor

The design borrows Harbor's task format and egress design without adopting
its runtime. If the group wants Repère-RCA tasks submitted to a Harbor
Hub dataset or run under Harbor's sandbox backends, the exporter in
DESIGN.md §5.1 moves up the list. Needed: yes or no for now.

## Q14. Existing repere documentation drift found on the way

Not questions, but decisions to confirm: README says a 13-model registry
(the file has 15 cards); the documented `inspect eval <file>@task` path
fails on the relative imports in the suite modules under inspect_ai
0.3.263 (programmatic `inspect_ai.eval` works); the `gaia_data_downloader`
`inspect_tasks.py` is a stub that raises. Fix now, or leave for the
maintenance branch?
