# aRCADA (github.com/mhemmett/arcada): what the code and data actually contain

## 0. Basis for this report

| Item | Value | How verified |
|---|---|---|
| Clone | `git clone --depth 1 https://github.com/mhemmett/arcada` | run 2026-09-14 |
| HEAD | `14294bca45ce5f65fd6541bea68ab40fbc870659` | `git log -1` |
| HEAD date | 2026-06-04 23:37:42 -0700, "Merge pull request #56 from mhemmett/fix-blog-captions" | `git log -1` |
| Default branch | main (9 other feature branches exist) | `git ls-remote` |
| Repo created | 2026-05-19T19:32:13Z, as a fork of `ajm-glitch/arcada` (created 2026-05-12T17:20:09Z) | `gh api repos/mhemmett/arcada` |
| Commits | 163 total; contributors mhemmett 55, github-actions[bot] 12, ajm-glitch 4 | `gh api .../commits`, `.../contributors` |
| Course context | "CSE 599 M · Spring 2026 · University of Washington", authors Michael Hemmett and Anjani Mirchandani | blog/index.html:372-374 |
| Team | Hemmett "UW ESS Graduate Student ... Works with Marine Denolle ... and William Wilcock"; Mirchandani "UW AMATH Undergraduate Student ... Works with Marine Denolle" | index.html:1581-1588 |

Every claim below was checked by reading the file at this commit or by running Python over the JSON files in the clone. Nothing was executed against Gemini, OOI, FDSN, or Cloudflare. Items I could not confirm are marked NOT VERIFIED. Paths are relative to the clone root `<scratch>/arcada/`.

## 1. File inventory (48 tracked files)

| Path | Size | Role |
|---|---|---|
| `README.md` | 6.3 KB | overview (several stale statements, section 10) |
| `LICENSE` | MIT, "Copyright (c) 2026 Anjani Mirchandani" | code license |
| `index.html` | 58 KB | marketing/About page with a canned fake chat demo |
| `blog/index.html` + 6 PNG | 22 KB + 8.2 MB | blog post |
| `chat/index.html`, `chat/chat.js` (1297 lines), `chat/chat.css`, `chat/config.json` | 58 KB js | the live assistant UI |
| `worker/src/index.js` (488 lines), `worker/wrangler.toml`, `worker/.dev.vars.example` | 23 KB | Cloudflare Worker proxying Gemini and GitHub |
| `catalog/instruments.json` | 111 KB | 120 instruments |
| `catalog/pi-pages.json` | 3 KB | 6 PI-portal scraper hints |
| `catalog/papers.json` | 279 KB | 142 papers from Zotero |
| `catalog/pdf-chunks.json` | 1.58 MB | 493 full-text chunks from 18 PDFs |
| `catalog/m2m-metadata.json` | 44 B | empty: `{"version": "1.0", "instruments": {}}` |
| `catalog/rca-context.json` | 40 KB | 3 scraped oceanobservatories.org pages |
| `catalog/pdfs/.gitignore` (`*.pdf`) | | PDFs are not in the repo |
| `public/chunks.json` | 1.95 MB | 802 built chunks, the only file the UI loads for retrieval |
| `public/embeddings.bin` | 2.46 MB = 802 x 768 float32 | built, never read by the UI |
| `public/search-index.json` | 1.79 MB | built, never read by the UI |
| `public/embed-hashes.json` | 70 KB | embedding cache keys |
| `scripts/build-index.mjs` (488 lines) | | builds `public/*` |
| `scripts/fetch-zotero.py`, `chunk-pdfs.py`, `fetch-m2m-metadata.py`, `fetch-rca-pages.py`, `patch-paper-meta.mjs` | | catalog builders |
| `data-pulls/dispatcher.py`, `ooi_api.py`, `earthscope.py`, `pi_scraper.py`, `to_zarr.py`, `requirements.txt` | | server-side fetch pipeline (not wired to the UI) |
| `.github/workflows/build-index.yml`, `fetch-data.yml` | | CI |
| `package.json` (minisearch ^7.1.0, wrangler ^4.93.0), `rag-config.json`, lockfiles | | |

No tests, no eval, no notebooks, no Dockerfile, no CITATION file.

## 2. Architecture (a)

### 2.1 Frontend
Static HTML/JS. `chat/index.html:104` loads MiniSearch 7 from `cdn.jsdelivr.net/npm/minisearch@7`; `chat/chat.js:84-87` fetches `config.json` then `../public/chunks.json` and builds two MiniSearch indexes in the browser (section 3). `chat/config.json:2` points at the worker: `https://arcada-data-assistant.michaelahemmett.workers.dev`. The blog says the site is on GitHub Pages (blog/index.html:431); `.nojekyll` is present.

Three modes (chat/index.html:69-71): "Ask a Question", "Literature Review", "Access Data". A client-side regex classifier (chat.js:1087-1120) picks DATA_REQUEST / LITERATURE / CAPABILITY / QUESTION / AMBIGUOUS; the mode buttons override it (chat.js:1211-1213). CAPABILITY returns a hard-coded string with no retrieval and no model call (chat.js:1192-1223).

### 2.2 Worker routes (worker/src/index.js:460-481) and which ones the UI uses

| Route | Handler | Model call | Called by chat.js at HEAD? |
|---|---|---|---|
| GET /health | inline | none | defined in `probeWorker` (167-172) but that function is never called |
| POST /embed | 89-105 | `gemini-embedding-2:embedContent`, 768-d | no |
| POST /welcome | 108-141 | `gemini-2.0-flash-lite:generateContent`, T=0.7 | no; welcome is a static string (chat.js:176-182) |
| POST /chat | 144-220 | streaming, see below | yes, the only route used (chat.js:211-218, 1130) |
| POST /ack | 415-457 | generateContent via fallback chain, T=0.5, maxOutputTokens 100 | no |
| POST /plan | 224-313 | generateContent, T=0.1, `responseMimeType: application/json` | no |
| POST /dispatch | 317-363 | none (GitHub API) | no |
| GET /status/:runId | 367-411 | none (GitHub API) | no |

Verified by grepping chat.js: the only worker paths that appear are `/chat` and `/health`. `workerPost`, `renderDataPlan`, `generateDataScript`, `downloadFile`, `showRelatedPapers`, `probeWorker` are defined and never called.

### 2.3 /chat model call (index.js:144-220)
- Model chain `FALLBACK_MODELS` (index.js:10-16): `gemini-2.0-flash-lite`, `gemini-2.0-flash`, `gemini-2.5-flash-lite`, `gemini-2.5-flash`, `gemini-1.5-flash`. On HTTP 429 it moves to the next model; on 503 it retries the same model up to 3 times honoring `Retry-After` (191-205).
- Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key=...` (192-194). The API key is a URL query parameter.
- `generationConfig: { temperature: 0.3 }` (184). No max tokens, no safety settings, no tools.
- `system_instruction` = `SYSTEM_PROMPT` (index.js:41-68), verbatim:

```
You are aRCADA, an expert data assistant for the OOI Regional Cabled Array (RCA) and EarthScope seafloor observatory networks on the Cascadia margin.

## Instruments you can access
- **Ocean bottom seismometers (OBS / seismometer)** — earthquakes, tremor, volcanic eruptions at Axial Seamount and Hydrate Ridge
- **Seafloor pressure sensors (BOTPT)** — seafloor deformation, slow-slip events, tidal loading
- **CTD profilers** — ocean temperature, salinity, and pressure through the water column
- **Hydrophones** — acoustic signals from methane bubble plumes, earthquakes, fin whales, and cetaceans
- **pCO2 sensors** — dissolved carbon dioxide near methane seeps
- **PI-operated instruments** — scanning sonar (Hydrate Ridge), mass spectrometers (ASHES vent field), and other portal-hosted data

## Key sites
Axial Seamount (active submarine volcano), Hydrate Ridge (methane seep field), ASHES hydrothermal vent field, Southern Hydrate Ridge, Endurance Array offshore Oregon.

## How to respond

**Capability questions** ("what can you do?", "what data is available?", "what instruments are there?"):
Describe the instrument types, sites, and research topics above. Mention that you can pull time-series data and link researchers to relevant published literature. Be concise and inviting.

**Literature / paper questions** ("what papers have been published on X?", "what research exists on Y?", "summarize the literature on Z?"):
Use the [paper] entries in the context below to answer. For each relevant paper, cite it as "Author et al. (Year) — Journal" and give a one-sentence summary of its finding. Group by sub-topic if helpful. If no papers are in context, say so honestly and suggest the user try a more specific query.

**Data requests** ("get me pressure data from...", "fetch seismic records for...", "show me data from..."):
Summarize the matched instruments: what each one measures, its location and depth, the time range it has been active, and where its data is stored (OOI M2M API, EarthScope FDSN, or a PI portal URL). Do not attempt to fetch or return any data yourself. Tell the user that the matched instruments are shown in the panel on the left and that a ready-to-run Python download script is shown below.

**Follow-up / conversational turns**:
Use prior conversation context to give coherent, non-repetitive replies.

Respond clearly and concisely. Never invent instrument IDs or paper citations that are not in the provided context.
```

The prompt mentions "Endurance Array"; the catalog contains no CE* Endurance site codes (all OOI sites are RS0*, section 4).

- `contents` = pruned history (chat.js:59-71: 6,000-char budget, keeps at least 2 entries; seeded with a fake "Hello!"/welcome pair at chat.js:180-181) followed by one user turn whose text is `query + contextBlock` (index.js:172-179). Context formatting is in section 3.4.

### 2.4 Build-time embedding call (scripts/build-index.mjs)
`gemini-embedding-2:batchEmbedContents` (line 30), `taskType: RETRIEVAL_DOCUMENT`, `outputDimensionality: 768` (313-319), L2-normalised (342-345), Float32 row-major to `public/embeddings.bin` (462-467), SHA-1 content-hash cache in `embed-hashes.json` (369-398). Triggered by `.github/workflows/build-index.yml` on pushes to `catalog/**`, `scripts/**`, `rag-config.json`; it commits `public/` back with `[skip ci]` (lines 37-43). The 12 github-actions[bot] commits confirm it has run. `rag-config.json:2` names `text-embedding-004`, but build-index.mjs reads only `CONFIG.batchSize` (line 428); `embedModel`, `chunkWords`, `overlapWords`, `minChunkWords` are dead config. The embeddings are never consumed: chat.js contains no reference to `embeddings.bin`, `/embed`, or any similarity computation.

### 2.5 Secrets and auth surface

| Secret | Where set | Where read |
|---|---|---|
| `GEMINI_API_KEY` | Cloudflare secret (README:98-101, wrangler.toml:9); GitHub Actions secret (build-index.yml:34) | index.js:94,126,194,24; build-index.mjs:24,30 |
| `GITHUB_PAT`, `GITHUB_REPO_OWNER`, `GITHUB_REPO_NAME` | Cloudflare secrets (wrangler.toml:10-12) | index.js:321-323, 368-370 |
| `OOI_USERNAME`, `OOI_TOKEN` | GitHub Actions secrets (fetch-data.yml:30-31) | dispatcher.py:87-88, ooi_api.py:187, fetch-m2m-metadata.py:26-35 |
| `CHAT_PASSWORD` | documented (wrangler.toml:13, .dev.vars.example:5) | never read; `timingSafeEqual` (index.js:483-488) is never called |

`ALLOWED_ORIGIN = "*"` (wrangler.toml:6, index.js:72). No route checks any credential. Since the worker URL is in the public `chat/config.json`, anyone can call `/dispatch` and trigger the owner's GitHub Actions workflow, and `/status` returns artifact metadata. No secret values are committed (`worker/.dev.vars` is gitignored, .gitignore:3).

## 3. Retrieval (b)

### 3.1 Engine
MiniSearch only (package.json:10 `"minisearch": "^7.1.0"`; browser build from jsDelivr). The README, comments and blog call it "BM25"; MiniSearch's ranking is BM25-based per its own documentation, but the repo does not configure or reference a scorer, so "BM25" here means "MiniSearch default" (NOT VERIFIED beyond the library default). No vector search, no hybrid fusion, no reranker, no query rewriting. `public/search-index.json` (a plain document dump written by build-index.mjs:349-363) is not a serialised MiniSearch index and is not loaded by the UI.

### 3.2 Two indexes, built at page load (chat.js:101-139)

| | Instrument index (`miniSearch`) | Paper index (`paperSearch`) |
|---|---|---|
| Documents | every unique chunk with `type !== "paper"`: 181 instrument chunks, 3 site-context, 3 script (187 total) | one doc per paper: chunks concatenated, `text` capped at 3000 chars (line 136); 134 docs |
| fields | `title, text, keywords, type, location` (104) | `title, text, keywords` (122) |
| boost | title 2, keywords 1.5 (106) | title 3, keywords 1.5 (124) |
| fuzzy | 0.2 (106) | 0.2 (124) |
| tokenizer / stemming | MiniSearch defaults; nothing custom configured | same |
| top-k | 8, then drop results below 20% of the top score (186-189, 73-78, 1229) | 4, no cutoff (191-193, 1230) |

### 3.3 Verified index-alignment defect
`bm25Search` returns `r.id` = position in the deduplicated non-paper list (chat.js:108-116, 187), but `handleNewQuery` uses it to index the full `CHUNKS` array (chat.js:1229: `CHUNKS[idx]`). Replicating `boot()` in Python over `public/chunks.json`: positions 0-180 align; positions 181-186 do not. Cause: `public/chunks.json` contains 6 duplicate IDs (`PI-OVRSRA101, PI-QNTSRA101, PI-COVIS, PI-DAS-OPTASENSE, PI-DAS24, PI-DAS25`) at array positions 181-186 because build-index.mjs:64 concatenates `CATALOG.instruments` and `PI_PAGES.instruments` and both files carry those IDs; the pi-pages copies have no `type`/`source` (those keys don't exist in pi-pages.json). The dedup in chat.js removes them, shifting the 3 site-context chunks and 3 script chunks to miniSearchIds 181-186, which then resolve to the six PI duplicates. Effect: a hit on the RCA overview text or the three "how to download" script chunks is displayed and sent to the model as a PI DAS/sonar instrument. The 181 real instrument chunks are unaffected.

### 3.4 Exactly what reaches the model
1. chat.js:1233-1235: `context = [...instrChunks(≤8), ...paperChunks(≤4)]`, papers first in literature mode.
2. chat.js:47-57, 1248: `trimContext` walks that list, summing `chunk.text.length`, and stops at the first chunk that would exceed 18,000 chars (constant at line 32).
3. Worker index.js:148-170 splits by `type` and formats:
   - instruments: `## Relevant instruments` then per chunk `- **{title}** ({location or source}): {text}`;
   - papers: `## Relevant papers from the literature` then `- **{title}** — {first_author}, {journal}, {year}` newline two spaces + `text.split("\n\n")[1] || text.slice(0, 400)` (for Zotero docs that is the abstract plus "Relevant instruments: ..." line; for PDF docs it is usually the first 400 chars of concatenated body text);
   - site-context: `## Background` + text;
   - whole block truncated at 20,000 chars with `[context truncated]` (18, 168-170).
4. The block is appended to the user's query string in the final user turn (179). The `::params` chunk type never appears because `m2m-metadata.json` is empty.

An instrument chunk's `text` as stored in `public/chunks.json` (verbatim, `RS01SLBS-LJ01A-09-HYDBBA102`):

```
Name: Oregon Slope Base Seafloor Broadband Hydrophone
Type: hydrophone
Location: Oregon Slope Base Seafloor
Source: earthscope
Description: Broadband hydrophone on profiler recording acoustic signals across a wide frequency range
Keywords: hydrophone, acoustic, broadband, ambient sound, marine mammal, oregon slope base seafloor
Latitude: 44.5101
Longitude: -125.3899
Depth: 2906 m
Data available from: 2015-04-01
Units: "Pa"
Sample rate: 200 Hz
OOI site: RS01SLBS / node: LJ01A
```

Template is `instrumentToText` (build-index.mjs:38-58). A second `{id}::desc` chunk is added when `description` exceeds 100 chars (95-107).

`expandSeismometersByLocation` (chat.js:794-815) adds every EarthScope catalog entry whose `location` starts with the same first word as a top-4 EarthScope hit, but only for the left panel and the script (`displayContext`, 1238-1242, 1262), not for the model context (1248).

## 4. Instrument catalog (c)

### 4.1 File and schema
`catalog/instruments.json`: `{ "version": "2.0", "description": "OOI Regional Cabled Array and EarthScope instrument registry for aRCADA", "instruments": [120] }`.

| Field | Count of 120 | Notes |
|---|---|---|
| id, name, type, source, location, latitude, longitude, depth_m, description, keywords, start_date | 120 | depth_m is null for 3 DAS entries; 95/120 have start_date `2015-04-01` |
| site, node, instrument | 99 | OOI reference-designator parts (`instrument` = e.g. `01-CTDPFL104`) |
| sample_rate_hz | 97 | |
| stream | 97 | OOI stream name |
| units | 74 | string or dict |
| ooi_page | 50 | Data Explorer or instrument-class URL |
| network, station, channels, sample_rates_hz, fdsn_url | 14 | the `EARTHSCOPE-OO-*` stations |
| fdsn_network, fdsn_station, fdsn_channels | 7 | OOI hydrophones served by FDSN |
| pi_base_url, instrument_code, format | 7 | PI portal entries |
| directory_pattern | 6 | |
| end_date | 2 | AXCC2 (2021-08-27), PI-DAS25 (2026-01-28) |

No `provenance`, `attribution`, `citation`, `verified`, `status`, `method`, or `notes` fields exist.

### 4.2 Contents

| Dimension | Values |
|---|---|
| source | ooi_api 92, earthscope 21 (14 stations + 7 hydrophones), pi_html 7 |
| type (25) | seismometer 13, ctd 12, fluorometer 12, hydrophone 9, velocimeter 8, dissolved_oxygen 8, adcp 8, pressure 7, camera 6, spectrophotometer 6, ph 4, thermistor 3, sonar 3, das 3, nitrate 2, pco2 2, hpies 2, mass_spectrometer 2, osmotic_sampler 2, irradiance 2, par 2, thermistor_array 1, tiltmeter 1, dna_sampler 1, fluid_sampler 1 |
| OOI site codes (13) | RS01SBPS 19, RS03AXPS 18, RS01SLBS 9, RS03AXBS 9, RS01SBPD 8, RS03INT1 7, RS01SUM2 6, RS03AXPD 6, RS03ASHS 5, RS01SUM1 3, RS03CCAL 3, RS03ECAL 3, RS03INT2 3 |
| nodes (18) | SF01A, SF03A, PC01A, PC03A, DP01A, DP03A, MJ03C, LJ01A, MJ01B, LJ03A, MJ03B, MJ01A, LJ01B, MJ03A, MJ03F, MJ03E, MJ03D, PN03B |
| FDSN stations (network OO) | AXAS1, AXAS2, AXBA1, AXCC1, AXCC2 (tiltmeter), AXEC1, AXEC2, AXEC3, AXID1, HYS11, HYS12, HYS13, HYS14, HYSB1 |
| FDSN channels | 13 x `BHZ,BHN,BHE` at 40 Hz; AXCC2: `BNE,BNG,BNN,BNZ,BKA,BXG,MKA,MNE,MNG,MNN,MNZ,MXG` at 40/8 Hz; hydrophones `HDH,LDH` |
| OOI instrument classes in IDs | CTDPFL/A/B, VEL3DA/B, FLCDRA, FLNTUA, DOSTAD, DOFSTA, ADCPTD/TE/SK, VADCPA/B, HYDBBA, HYDLFA, PHSENA, FLORDD, FLORTD, NUTNRA, VELPTD, PCO2WA, HPIESA, PRESTA/B, BOTPTA, TMPSFA, THSPHA, TRHPHA, MASSPA, OSMOIA, OPTAAC/D, CAMDSB/C, CAMHDA, SPKIRA, PARADA, FLOBNC/M, PPSDNA, RASFLA |
| stream names (28) | ctdpf_optode_sample 12, do_stable_sample 8, adcp_velocity_beam 8, botpt_nano_sample 7, vel3d_b_sample 6, optaa_dj_dcl_instrument 6, hydlf_a_dcl_instrument 5, hydbba_a_dcl_instrument 4, phsen_data_record 4, camds_a_video 4, flcd_r_dcl_instrument 3, flntu_a_dcl_instrument 3, flord_d_data_record 2, flort_d_data_record 2, nutnr_a_sample 2, velpt_velocity_data 2, pco2w_a_sami_data_record 2, horizontal_electric_field 2, trhph_sample 2, dissgas_instrument_recovered 2, spkir_a_dcl_instrument 2, parad_k_stc_imodem_instrument 2, flort_dj_dcl_instrument 2, tmpsf_sample 1, thsph_a_dcl_instrument 1, camhd_a_video 1, pps_dna_instrument 1, rasfl_a_dcl_instrument 1 |
| location strings (14) | Oregon Slope Base 28, Axial Seamount Profiler 18, Southern Hydrate Ridge Summit 13, Axial Seamount International District 11, Axial Seamount Base 10, Oregon Slope Base Seafloor 9, ASHES Hydrothermal Field, Axial Seamount 8, Axial Seamount Deep Profiler 6, Axial Seamount Eastern Caldera 6, Axial Seamount Central Caldera 5, Southern Hydrate Ridge 3, three DAS cable descriptions |
| PI entries | PI-OVRSRA101, PI-QNTSRA101, PI-CAMPIA101 (MARUM, Hydrate Ridge), PI-COVIS, PI-DAS-OPTASENSE, PI-DAS24, PI-DAS25 |
| external URLs | `https://ds.iris.edu/mda/OO/{STA}/?starttime=...` (14); `https://dataexplorer.oceanobservatories.org/#ooi/array/{RSAXIAL|RSMARGIN}/instrument_type/{CTD|FLUOR|MASSP|OSMOI}...` (8 distinct); `https://oceanobservatories.org/instrument-class/{camds,camhd,optaa,parad,ppsdn,rasfl,spkir}/`; `https://oceanobservatories.org/pi-instrument/...` (5); `http://piweb.ooirsn.uw.edu/{marum/data/OVRSRA101,marum/data/QNTSRA101,marum/data/CTDPFA110,marum/data/CAMPIA101,das/data/Optasense,das24/data,das25/data}/`; `http://piweb.ooirsn.uw.edu/covis/data/COVIS/` (pi-pages.json:41) |

Whether every stream name and ref-des is valid in OOI M2M: NOT VERIFIED (no live calls made).

### 4.3 Three short verbatim entries

```json
{
  "id": "RS01SUM1-LJ01B-09-PRESTB102",
  "name": "Southern Hydrate Ridge Flank Seafloor Pressure",
  "type": "pressure",
  "source": "ooi_api",
  "site": "RS01SUM1",
  "node": "LJ01B",
  "instrument": "09-PRESTB102",
  "location": "Southern Hydrate Ridge",
  "latitude": 44.5664,
  "longitude": -125.1467,
  "depth_m": 780,
  "description": "Seafloor pressure sensor",
  "keywords": ["pressure", "seafloor", "southern hydrate ridge"],
  "units": "psia",
  "sample_rate_hz": 1,
  "start_date": "2015-04-01",
  "stream": "botpt_nano_sample"
}
```

```json
{
  "id": "RS01SUM2-MJ01B-12-ADCPSK101",
  "name": "Southern Hydrate Ridge Summit ADCP",
  "type": "adcp",
  "source": "ooi_api",
  "site": "RS01SUM2",
  "node": "MJ01B",
  "instrument": "12-ADCPSK101",
  "location": "Southern Hydrate Ridge Summit",
  "latitude": 44.5691,
  "longitude": -125.1479,
  "depth_m": 775,
  "description": "Acoustic Doppler Current Profiler on seafloor",
  "keywords": ["adcp", "current", "velocity", "southern hydrate ridge summit"],
  "units": "m/s",
  "sample_rate_hz": 1,
  "start_date": "2015-04-01",
  "stream": "adcp_velocity_beam"
}
```

```json
{
  "id": "EARTHSCOPE-OO-AXCC1",
  "name": "Axial Seamount Central Caldera Seismic Station AXCC1",
  "type": "seismometer",
  "source": "earthscope",
  "network": "OO",
  "station": "AXCC1",
  "location": "Axial Seamount Central Caldera",
  "latitude": 45.954683,
  "longitude": -130.008979,
  "depth_m": 1527.0,
  "description": "Broadband seismometer at Axial Seamount Central Caldera recording volcanic seismicity, eruptions, and tectonic earthquakes",
  "keywords": ["seismometer", "earthquake", "seismic", "axial seamount", "volcano", "eruption", "tremor", "axial seamount central caldera"],
  "channels": ["BHZ", "BHN", "BHE"],
  "sample_rates_hz": [40],
  "start_date": "2014-07-25",
  "fdsn_url": "https://ds.iris.edu/mda/OO/AXCC1/?starttime=2014-07-25T21:05:00&endtime=2599-12-31T23:59:59"
}
```

Note the first entry: a PREST (Sea-Bird pressure) instrument assigned the BOTPT stream `botpt_nano_sample`. Whether that is a valid pairing: NOT VERIFIED, but `STREAM_OVERRIDES` in chat.js:331-332 and ooi_api.py:40-41 map PRESTA/B to `prest_real_time`, so the catalog and code disagree.

### 4.4 How it was built
No script in the repo produces `instruments.json`. Commit history on the file (GitHub API, path filter):

| Commit | Date | Message |
|---|---|---|
| 9bae239a | 2026-05-19 | Add aRCADA framework: RAG index, Cloudflare Worker, data pull scripts, chat UI |
| 0f041d5b | 2026-05-20 | Expand instrument catalog to 98+ instruments and switch to gemini-embedding-2 |
| 7601a44f | 2026-06-01 | Fix seismometer catalog: add IRIS MDA links, AXCC2, correct PI locations and broken URLs |
| 044a29e5 | 2026-06-01 | Remove MARUM contact note from null pi_base_url fields |
| b104d32c | 2026-06-01 | Update instrument catalog: links, removals, and new instruments |
| d0c5ca53 | 2026-06-01 | Remove RASSP; add 22 missing RCA instruments with verified links |
| 08f0c92a | 2026-06-01 | Fix instrument card bugs, script generation, and rendering |
| 5535d1f5 | 2026-06-01 | Rename DAS Optasense instrument from 2021+ to 2025+ |
| ab47afaf | 2026-06-02 | Remove ASHES PI CTD and add Gemini Embedding TPM throttle |

That is consistent with hand curation in an editor (possibly LLM-assisted: the parent repo's first UI commit is "added Claude-generated UI - change later", 2f12076a, but nothing evidences LLM authorship of the catalog; NOT VERIFIED either way). The blog says the catalog is "built with instrument specifications and descriptions from the RCA website, alongside specific metadata pulled from data storage locations" (blog/index.html:416). The one enrichment script, `scripts/fetch-m2m-metadata.py`, would call `{M2M}/{site}/{node}/{instrument}/metadata` per instrument with OOI basic auth (lines 24-35, 81) and write `parameters` + `streams`, but its output `catalog/m2m-metadata.json` is empty, so no M2M-derived parameter text is in the index. Descriptions credit PIs in prose (e.g. "Developed by Dr. Yann Marcon and Prof. Gerhard Bohrmann (MARUM, University of Bremen), funded by German BMBF" in PI-OVRSRA101; "Peter Girguis, Harvard University" in RS03INT1-MJ03C-06-MASSPA301; "Nokia Bell Labs ... GitHub: https://github.com/uwfiberlab/OOI_DAS_2025" in PI-DAS25). No OOI data-use or citation statement anywhere in the repo.

Dangling IDs: `scripts/fetch-zotero.py:24-62`, `scripts/fetch-rca-pages.py:36-53`, `catalog/rca-context.json` and `catalog/papers.json[*].linked_instruments` reference IDs that are not in the current catalog. `EARTHSCOPE-OO-HYS14` and `PI-OVRSRA101` exist, but `PI-MASSP-ASHES`, `RS01SUM1-LJ01B-10-PCO2WA101`, `RS01SUM2-MJ01B-09-THSPHD000`, `RS01SUM2-MJ01B-12-HYDMGA000`, `RS01SUM2-MJ01B-14-BOTPTA301`, `RS01SUM2-MJ01B-15-OBSBBA102`, `RS03ASHS-MJ03B-10-THSPHD000`, `RS03ASHS-MJ03B-15-OBSSPA301`, `RS03AXBS-LJ03A-12-HYDLFA301`, `RS03AXBS-LJ03A-14-BOTPTA301`, `RS03AXPS-PC03A-4B-CTDPFK301` do not (they look like an earlier catalog version). So most paper-to-instrument links in `papers.json` point at nothing.

`catalog/pi-pages.json` (version "2.0", 6 entries) holds scraper hints, e.g.:

```json
{
  "id": "PI-QNTSRA101",
  "instrument_code": "QNTSRA101",
  "name": "Hydrate Ridge Rotary Sonar",
  "base_url": "http://piweb.ooirsn.uw.edu/marum/data/QNTSRA101/",
  "index_type": "apache_directory",
  "directory_pattern": "{YYYY}/{MM}/",
  "file_extension": ".smb",
  "file_format": "binary_sonar",
  "parse_strategy": "binary_numeric_regex",
  "time_resolution": "per_scan",
  "notes": "Binary sonar scan files at 20-minute intervals. Require binary parser for .smb format."
}
```

## 5. Paper index (d)

### 5.1 `catalog/papers.json`
`{ "version": "1.0", "source": "Zotero OOI-RCA collection", "papers": [142] }`. Every entry has exactly these keys: `title, abstract, doi, year, journal, first_author, tags, linked_instruments, pdf_path`.

| Statistic | Value |
|---|---|
| papers | 142 |
| with DOI | 141 |
| non-empty abstract | 131 |
| year non-null | 142; range 2013-2025 |
| year histogram | 2013:1, 2014:2, 2015:1, 2016:7, 2017:4, 2018:15, 2019:19, 2020:13, 2021:15, 2022:29, 2023:15, 2024:9, 2025:12 |
| pdf_path non-null | 18 (absolute paths under `/Users/mhemmett/Zotero/storage/`) |
| linked_instruments non-empty | 122 (but see dangling IDs above) |
| top journals | Frontiers in Marine Science 11, JGR Solid Earth 11, GRL 9, Oceanography 8, JASA 7, J. Mar. Sci. Eng. 6, Earth and Space Science 6, G-cubed 6+5 (two spellings), JASA Express Letters 5 |

### 5.2 How it was built
`scripts/fetch-zotero.py` copies `~/Zotero/zotero.sqlite` (line 16), selects collections named `OOI RCA` / `OOI-RCA` (20), pulls `title, abstractNote, DOI, date, url, publicationTitle` (112), first author's last name (148-159), tags, and the first stored PDF attachment path (119-134). `year` is the first `(19|20)\d{2}` match in Zotero's free-text `date` (171-172); no month or day is kept. `linked_instruments` come from a hard-coded keyword map (24-71). No bibliographic API is used: grep for openalex, crossref, semanticscholar, arxiv, pyzotero over all source and doc files returns nothing. Re-running requires the authors' local Zotero library; there is no date-cutoff option. A cutoff can be applied post hoc only at year granularity by filtering `papers.json` on `year`, after which `node scripts/build-index.mjs` rebuilds `public/` (it exits without `GEMINI_API_KEY`, build-index.mjs:33, even though the embeddings it produces are unused).

### 5.3 Full text
`scripts/chunk-pdfs.py` (PyMuPDF; 400-word chunks, 50-word overlap, lines 35-36; header/footer stripping 41-52) processes PDFs in `catalog/pdfs/` and the Zotero `pdf_path`s, matching to `papers.json` by exact lower-cased title (83-89). Output `catalog/pdf-chunks.json`: 493 chunks from 18 documents with keys `id, title, doi, year, journal, first_author, tags, linked_instruments, chunk_index, chunk_total, text`. Only 8 of 18 matched Zotero (DOI/year/journal present); the other 10 have null DOI/year/journal and titles derived from the filename (build-index.mjs:167-187 later tries to recover metadata from a DOI in the body). The 18:

| id base | DOI | year | journal | chunks |
|---|---|---|---|---|
| Ragland and Abadi 2025, wind-dependent ambient sound | none | none | none | 13 |
| 10.1007/s44267-025-00085-y (Ding, DASFormer) | yes | 2025 | Visual Intelligence | 32 |
| 10.1126/science.adh9607 (Vance, Big data in Earth science) | yes | 2024 | Science | 23 |
| Lapins et al. 2024, DAS-N2N | none | none | none | 37 |
| Gemba et al. 2023, Kauai-Beacon m-sequence | none | none | none | 12 |
| 10.1029/2023JB026413 (Cook) | yes | 2023 | JGR Solid Earth | 35 |
| Dølven et al. 2022, Svalbard methane seep | none | none | none | 37 |
| Ragland et al. 2022, OOI hydrophone ambient sound | none | none | none | 31 |
| Xu et al. 2021, hydrothermal discharge (OOI) | none | none | none | 33 |
| Schwock and Abadi 2021, rain noise | none | none | none | 34 |
| 10.1029/2020gl088447 (Moyer) | yes | 2020 | GRL | 19 |
| Lee and Staneva 2020, echosounder time series | none | none | none | 32 |
| Doran and Crawford 2020, crustal structure after eruption | none | none | none | 14 |
| 10.3389/fmars.2019.00260 (Frajka-Williams) | yes | 2019 | Front. Mar. Sci. | 45 |
| 10.3389/fmars.2019.00093 (Barth) | yes | 2019 | Front. Mar. Sci. | 28 |
| 10.1029/2018GL078233 (Saunders) | yes | 2018 | GRL | 18 |
| 10.1002/2016jc012464 (Xu) | yes | 2017 | JGR Oceans | 33 |
| Alford et al. 2015, inductive charging profiler | none | none | none | 17 |

Open-access status of these 18: NOT VERIFIED (blog/index.html:416 claims full text only for open-access papers; Science and JGR titles are in the list).

In the built index (`public/chunks.json`) papers appear as 609 chunks: 116 Zotero abstract-only documents (`source: "zotero"`, one chunk each, `id: paper::{doi}`) plus the 493 PDF chunks, so 134 distinct papers are searchable. build-index.mjs:213-240 skips the abstract chunk when a PDF with the same DOI exists and skips abstracts shorter than 80 chars.

### 5.4 Three verbatim entries (shortest)

```json
{
  "title": "Tracking Microbial Evolution in the Subseafloor Biosphere",
  "abstract": "",
  "doi": "10.1128/msystems.00731-21",
  "year": 2021,
  "journal": "mSystems",
  "first_author": "Anderson",
  "tags": [],
  "linked_instruments": [],
  "pdf_path": null
}
```

```json
{
  "title": "Statistical analysis and modeling of underwater wind noise at the northeast pacific continental margin",
  "abstract": "",
  "doi": "10.1121/10.0007463",
  "year": 2021,
  "journal": "The Journal of the Acoustical Society of America",
  "first_author": "Schwock",
  "tags": [],
  "linked_instruments": [],
  "pdf_path": null
}
```

```json
{
  "title": "Efficient Sampling of Geophysical Sensor Arrays on the Seafloor",
  "abstract": "The great expense of deploying dense arrays of seafloor sensors for continuous collection of geophysical data inhibits the proliferation of measurement systems to the majority of the planet's surface. [...abstract continues...]",
  "doi": "10.1029/2025CN000288",
  "year": 2025,
  "journal": "Perspectives of Earth and Space Scientists",
  "first_author": "Zumberge",
  "tags": [],
  "linked_instruments": ["EARTHSCOPE-OO-AXCC1", "EARTHSCOPE-OO-AXEC2", "EARTHSCOPE-OO-AXID1", "EARTHSCOPE-OO-HYS14", "RS01SUM2-MJ01B-15-OBSBBA102"],
  "pdf_path": null
}
```

(The third abstract is truncated by me; everything else is verbatim.)

## 6. Code generation (e)

### 6.1 What runs in the live UI
`generateScript(instruments, query)` (chat.js:704-789), invoked by `renderScriptInChat` (825-883) only when the intent is DATA_REQUEST (1262). It takes the first two unique instrument chunks from the display context (830) and a date range from `extractDates` (607-668): the phrase "2015 ... eruption" maps to 2015-04-24 to 2015-05-09; two ISO dates; "spring/summer/fall/winter YYYY"; "N weeks/days/months after"; "Month YYYY"; "last N days"; otherwise the last 30 days. The script is never executed anywhere: it is rendered into a `<pre>` with a Copy button and a Blob download link (869-882). The model is told not to fetch data (SYSTEM_PROMPT) and any ```python block the model emits is stripped from the displayed prose (1252-1255).

Emitted header and OOI block (chat.js:713-730, 748-763), verbatim template with `${...}` placeholders:

```python
# aRCADA — auto-generated data pull script
# ${titles joined by " | "}

import os, requests
from obspy.clients.fdsn import Client as FDSNClient   # only if an earthscope instrument
from obspy import UTCDateTime                          # only if an earthscope instrument
from bs4 import BeautifulSoup                          # only if a pi_html instrument

START = "${start}T00:00:00"
END   = "${end}T23:59:59"

OOI_USER  = os.environ["OOI_USERNAME"]
OOI_TOKEN = os.environ["OOI_TOKEN"]
BASE      = "https://ooinet.oceanobservatories.org/api/m2m/12576/sensor/inv"

# ── ${title} (${location}) ──
url = (BASE
    + f"/${subsite}/${node}/${sensor}"
    + f"/${info.method}/${info.stream}"
    + f"?beginDT={START}&endDT={END}"
)
r = requests.get(url, auth=(OOI_USER, OOI_TOKEN), timeout=60)
r.raise_for_status()
with open("${id}.json", "w") as f: f.write(r.text)
print(f"Saved {len(r.json())} records — ${id}")
```

EarthScope block (chat.js:736-746):

```python
client = FDSNClient("EARTHSCOPE")
st = client.get_waveforms(
    network="OO", station="${station}", location="*",
    channel="${cfg.channel}",            # "BH?" seismometer/hydrophone, "BN?" tiltmeter (601-605)
    starttime=UTCDateTime(START), endtime=UTCDateTime(END)
)
st.write("${station}.mseed", format="MSEED")
print(f"Saved {len(st)} traces — ${station}")
```

PI block (chat.js:765-783): `requests.get(base_url)`, BeautifulSoup over `<a href>` entries, download each file; base URL from `chunk.pi_base_url`; else a comment "No programmatic URL for this instrument — access manually."

OOI `method`/`stream` come from `OOI_STREAMS` (chat.js:568-598) keyed by class code with fallback `{stream: "streamed_auto", method: "streamed"}` (754). That table uses `telemetered` for most classes and stream names (e.g. `ctdpf_sbe43_sample`, `hydbb_noisy_sample`, `do2_oxy_calphase`, `flort_sample`) that differ from both the catalog `stream` field and from `data-pulls/ooi_api.py:22-61`; `generateScript` ignores the catalog's `stream` field. Validity of those names against M2M: NOT VERIFIED.

Verified defect: for the 7 EarthScope-served hydrophones whose IDs are OOI ref-des strings, `station = id.replace("EARTHSCOPE-OO-", "")` (737) yields e.g. `station="RS01SLBS-LJ01A-09-HYDBBA102"`; the catalog's `fdsn_station` (e.g. `AXBA1`) is not copied into `public/chunks.json` (build-index.mjs:76-92 copies only `fdsn_url, pi_base_url, ooi_page`), so the generated FDSN request cannot succeed for those instruments.

### 6.2 Dead second generator
`generateDataScript(plan)` (chat.js:400-526) consumes a `/plan` JSON and emits `def fetch_<id>()` functions using `f"/{site}/{node}/{instr}/{method}/{stream}?beginDT=...&endDT=...&format=application/json&limit=20000"` with optional auth (433), `FDSNClient("EARTHSCOPE")` with `channel="BH*,HH*"` or `"HDH,LDH"` (449-459), and hard-coded `PI_BASE_URLS` (370-379). Never called.

### 6.3 Server-side execution path (present, not wired to the UI)
Worker `/dispatch` posts a `workflow_dispatch` to `fetch-data.yml` with the plan JSON (index.js:325-337), then returns the newest run id; `/status/:id` polls and returns the `arcada-data` artifact zip URL (index.js:367-411; artifact retention 7 days, fetch-data.yml:38-43). The workflow runs `data-pulls/dispatcher.py`, which loads the catalog (dispatcher.py:40-46), routes by `source` (34-38), writes per-instrument NetCDF then a single Zarr v2 store plus `arcada_{job}_metadata.json` with coverage, gaps, units, errors (to_zarr.py). The blog states this is "implemented but not yet integrated into the live demo" (blog/index.html:450). No frontend code calls `/plan` or `/dispatch`.

All hosts and URLs hard-coded or templated anywhere in the repo:

| Host / URL | Where |
|---|---|
| `https://ooinet.oceanobservatories.org/api/m2m/12576/sensor/inv` | chat.js:429,728; ooi_api.py:18; fetch-m2m-metadata.py:24; build-index.mjs:252 |
| `https://ooinet.oceanobservatories.org` (registration) | chat.js:503; build-index.mjs:253 |
| FDSN `Client("IRIS")` | earthscope.py:19; build-index.mjs:269 (script chunk text) |
| FDSN `Client("EARTHSCOPE")` | chat.js:454,739 (emitted scripts) |
| `https://ds.iris.edu/mda/OO/...` | catalog fdsn_url; chat.js:920 fallback |
| `http://piweb.ooirsn.uw.edu/{marum/data/OVRSRA101, marum/data/QNTSRA101, marum/data/CTDPFA110, marum/data/CAMPIA101, das/data/Optasense, das24/data, das25/data, covis/data/COVIS, scpr, a0a/data}/` | chat.js:371-378, 889-896; pi-pages.json; build-index.mjs:289-298 |
| `https://oceanobservatories.org/{regional-cabled-array, array/cabled-axial-seamount-array, array/cabled-continental-margin-array, instrument-class/*, pi-instrument/*}` | fetch-rca-pages.py:21-34; chat.js:889-931; catalog ooi_page |
| `https://dataexplorer.oceanobservatories.org/#ooi/array/{RSAXIAL,RSMARGIN}/...` | catalog ooi_page |
| `https://generativelanguage.googleapis.com/v1beta/models/...` | index.js:4-6,24,192; build-index.mjs:30 |
| `https://api.github.com` | index.js:7 |
| `https://doi.org/{doi}` | chat.js:547,938-944 |
| `https://cdn.jsdelivr.net/npm/minisearch@7`, `fonts.googleapis.com` | chat/index.html:7-9,104 |

## 7. Evaluation, tests, example queries, logged Q&A (f)

None of: unit tests, integration tests, eval scripts, golden question sets, benchmark files, or logs of real interactions. `find` for `*test*`, `*eval*`, `*golden*`, `*bench*` returns nothing; no CI step runs tests.

What exists:
- Four example-query buttons (chat/index.html:54-57): "Show me seismic and pressure data near Axial Seamount for the two weeks following the April 2015 eruption"; "I need hydrophone and pCO2 data from Hydrate Ridge from January to March 2021"; "Pull CTD profiles from the Axial Seamount profiler for summer 2022"; "Get scanning sonar data from the OVRSRA101 instrument from June through August 2019".
- Mode placeholders (chat.js:146-150) and the README's one example (README:29).
- The About page (`index.html`) has a `demoResponses` object with four canned exchanges whose values are fabricated (e.g. "CH₄ (dissolved) 482 nM — elevated", "Timestamp May 12, 2026", "Inflation rate +2.1 cm/month", and a Hydrate Ridge instrument labelled with the Endurance site code "CE04OSPS"). Its keys are `methane, temp, bio, tilt`, while the chips call `literature, explain, methane, vent` (index.html:1453-1456), so only "methane" renders; any typed question returns a fixed "This is a demo interface" message (index.html:1731). These are not outputs of the live system and should not be cited as such.
- The blog's "What Works Today" (blog/index.html:436-447) is qualitative; no accuracy or retrieval metrics anywhere.

## 8. Licensing and attribution (g)

- Code: MIT, `LICENSE:1-3`, copyright 2026 Anjani Mirchandani. Scope is "the Software"; no data license, no license notice in any JSON or in `public/`, no CITATION.cff, no mention of OOI or EarthScope data policies or citation requirements in README, blog or HTML (grep for license/credit/attribution/copyright over those files finds only the LICENSE file and the two ChatGPT captions).
- Third-party text redistributed in the repo: 131 publisher abstracts in `papers.json`; full text of 18 papers in `pdf-chunks.json` (open-access status NOT VERIFIED; the PDFs themselves are gitignored); about 9,000 chars scraped from three oceanobservatories.org pages in `rca-context.json` (including navigation chrome: "Skip to content Subscribe Access Data Help --> Menu The Observatory About OOI ..."); PI names and institutions in instrument descriptions.
- Images: 7 PNGs, all under `blog/`. Captions: `data_sources_arcada.png` "Figure 1" no credit (blog:399-400); `arcada_pipeline.png` "Figure 2 ... Diagram generated with ChatGPT" (420); `arcada_architecture.png` no credit (426-427); `arcada_title.png` alt "aRCADA interface screenshot" (379); `arcada_capabilities.png` screenshot (441); `offshore_figure.png` "Figure 3 ... Figure generated with ChatGPT" (464). No photographs of OOI/RCA hardware or NSF/OOI logos are present; `index.html` and `chat/index.html` contain no raster images (inline SVG icons only). Fonts are loaded from Google Fonts.

## 9. OOI M2M authentication, rate limits, FDSN clients (h)

M2M authentication:
- Emitted script: HTTP basic auth `auth=(OOI_USER, OOI_TOKEN)` from `os.environ["OOI_USERNAME"]` / `["OOI_TOKEN"]` (chat.js:726-727, 760); raises KeyError if unset. The header comment tells users to register at ooinet (503).
- Backend: `auth = (ooi_username, ooi_token) if ooi_username else None` (ooi_api.py:187), credentials from GitHub Actions secrets via env (dispatcher.py:87-88; fetch-data.yml:30-31). The worker never touches OOI credentials.
- `fetch-m2m-metadata.py:29-35` refuses to run without both env vars.
- Request shape: `.../{site}/{node}/{instrument}/{method}/{stream}?beginDT=...&endDT=...&format=application/json&limit=20000` (ooi_api.py:197-202), synchronous JSON only, 20,000-record cap; availability pre-check via `.../metadata` `times[]` (ooi_api.py:99-159). No asynchronous/NetCDF (THREDDS) request path, which the blog itself flags as needed (blog:450). Numeric columns matching `_qc_`, `_qartod_`, timestamps, `provenance` are dropped (226-230).
- Retries: 4 attempts with `2**attempt` s backoff on any `RequestException` (ooi_api.py:64-73; pi_scraper.py:29-39); `time.sleep(0.5)` between metadata calls (fetch-m2m-metadata.py:96). No OOI rate limit is otherwise modelled.

FDSN:
- Backend uses `obspy.clients.fdsn.Client("IRIS")` (earthscope.py:19,40,84,191), network `OO`, `location="*"`, channel priority `["BH*","HH*","EH*","SH*"]`, hydrophones `HDH,LDH` (23-25, 188, 234); day-by-day `get_waveforms` loop (91-117); `merge(method=1, fill_value=0)`, linear detrend, 5% Hann taper, 1 Hz highpass by default for seismometers (155-170); `get_stations(level="channel")` availability check (192-195). No token, no rate limiting, no `mass_downloader`.
- Emitted script uses `Client("EARTHSCOPE")` (chat.js:739) with `channel="BH?"` (602), whereas the "script" knowledge chunk text tells the model `Client("IRIS")` (build-index.mjs:269). Whether both aliases resolve identically in the installed ObsPy: NOT VERIFIED here.

Gemini rate handling: frontend enforces 2.5 s between calls, comment "30 RPM free tier" (chat.js:21-45), and a 15 s hold after a 429 (205, 1132); worker retries 503 up to 3 times per model and falls to the next model on 429 (index.js:21-39, 191-205); index build throttles to 28,000 tokens/min (build-index.mjs:419-450) and retries embeds 6 times with 30 s x attempt on 429 (313-340).

## 10. Discrepancies between documentation and code

| Claim | Where | Reality |
|---|---|---|
| `scripts/build_index.py` rebuilds chunks.json | README:121 | file does not exist; builder is `scripts/build-index.mjs` |
| "Embeddings are precomputed and stored in public/embeddings.bin" | README:82 | true, but never loaded; retrieval is MiniSearch only |
| `requests_futures` for OOI | README:45 | not used anywhere |
| RASSP fluid samplers via PI portal | README:47 | removed (commit d0c5ca53); `RS01SUM2-MJ01B-00-OSMOIA101` etc. are ooi_api |
| "Endurance Array" covered | README:49, SYSTEM_PROMPT | no CE* sites in catalog |
| `embedModel: text-embedding-004` | rag-config.json:2 | gemini-embedding-2 is used; config key ignored |
| Blog: "Separate BM25 searches ... four best-matched instruments and papers" | blog:423 | instruments k=8 with score cutoff, papers k=4 |
| Blog: "structured data plan showing exactly which instruments would be pulled" | blog:436 | `/plan` and `renderDataPlan` exist but are not called at HEAD |
| `CHAT_PASSWORD` "optional frontend password gate" | wrangler.toml:13 | never implemented |
| `catalog/m2m-metadata.json` "Parameters measured" enrichment | build-index.mjs:65-73, 109-125 | file is empty; no `::params` chunks exist |

## 11. Summary for the design document

aRCADA at commit 14294bc is a static MiniSearch-over-JSON retriever with a Cloudflare Worker that forwards one system prompt plus up to 18-20 k chars of catalog and paper text to `gemini-2.0-flash-lite` (falling back through four other Gemini models). It generates, but never runs, short Python snippets against three hosts (OOI M2M, EarthScope FDSN via ObsPy, piweb.ooirsn.uw.edu). The catalog is a hand-edited 120-entry JSON with no provenance fields; the paper set is a 142-entry Zotero export with year-only dates and no bibliographic API; the vector index and the structured `/plan` + GitHub Actions + Zarr pipeline exist in the tree but are disconnected from the UI. There are no tests, evaluations or interaction logs. Two verified defects affect what the model sees or what the script does: a 6-position index misalignment for site-context and script chunks, and missing FDSN station codes for the seven EarthScope-served hydrophones.