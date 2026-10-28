# Public releases on Hugging Face, with Croissant metadata and a DOI

Audience: whoever publishes a Repère golden set. Companion to
[`../holdout_policy.md`](../holdout_policy.md) (what stays hidden) and
[`README.md`](README.md) (the row format).

## What exists

| Hub repository | Visibility | DOI | Contents |
|---|---|---|---|
| `gaia-hazlab/repere-codameter` | public | yes, one per version | codameter dv/v tasks, public development split |
| `gaia-hazlab/repere-synthetic-stalta` | public | yes, one per version | synthetic STA/LTA tasks on a Ridgecrest record, public development split, plus the seed waveform |
| `gaia-hazlab/repere-hidden` | private | **never** | held-out test splits and the secret seed (`scripts/pull_eval_data.py`, `scripts/push_hidden_split.py`) |
| OOI Regional Cabled Array | not built | | placeholder in `datasets/releases.yaml`; RCA items are owned by RCA Atlas (ROADMAP P3.7) |

`datasets/releases.yaml` is the source of truth: one entry per DOI, with the
suites it contains, the license, the Responsible AI text, the readiness profile
and, after publishing, `hf_revision` and `doi`.

## What a release folder contains

`scripts/build_hf_release.py <name>` writes `build/hf/<name>/` (gitignored):

| File | Content |
|---|---|
| `data/<suite_id>.jsonl` | `BenchmarkRow` rows, split=validation and visibility=public only |
| `data/...` | extra files named in the entry (the synthetic STA/LTA seed waveform) |
| `manifest.json` | sha256 and row count per file; a score names the manifest it used |
| `croissant.json` | Croissant 1.1 with the RAI extension; GeoCroissant 1.0 when the entry has `geo` |
| `tasks.jsonld` | one Croissant Tasks `TaskProblem` per suite |
| `README.md` | dataset card: configs, scoring, license, readiness profile, citation |
| `LICENSE.md` | only for mixed terms (MIT rows plus source-data terms) |

### How the metadata maps onto the standards

- **Croissant 1.1** (`http://mlcommons.org/croissant/1.1`). One `FileObject`
  per file with its sha256, one `RecordSet` per suite, and a `cr:Split` record
  set. `gold`, `scorer_spec` and `metadata` are JSON objects whose shape
  differs between suites, so their sub-fields are derived from the rows
  (typed scalars, numeric arrays with `isArray`, nested objects through
  `jsonPath`).
- **RAI** (`rai:`). `dataCollection`, `dataCollectionType`, `dataLimitations`,
  `dataBiases`, `personalSensitiveInformation`, `dataUseCases`,
  `dataReleaseMaintenancePlan`, written per release in `releases.yaml`.
- **GeoCroissant 1.0** (`geocr:`, `http://mlcommons.org/croissant/geo/1.0`).
  schema.org `spatialCoverage` (station coordinates from the FDSN station
  service) and `temporalCoverage`, plus `geocr:coordinateReferenceSystem` and
  `geocr:temporalResolution` (the sampling interval). Releases with no place,
  such as the synthetic codameter cases, declare Croissant 1.1 only.
- **Croissant Tasks** (experimental upstream, `mlcommons/croissant/tasks/`).
  Each suite is a `TaskProblem`: the dataset as `input`, an `OutputSpec`
  (what the model returns), an `ImplementationSpec` (the system under test),
  an `ExecutionSpec` (repeats and temperature) and an `EvaluationSpec` (the
  scorer). This is the D1 "task record" of the AI-readiness instrument.
- **Readiness profile.** Evidence level per criterion (0, 1, 2, or not yet
  assessed) with the evidence named, never summed. It is a v0 self-assessment
  until someone outside the project reviews it.

Spec versions were read from `mlcommons/croissant` at commit `ec24358`
(2026-10-05). The generated files were checked with mlcroissant 1.1.1
(`mlcroissant validate`, and every record read back) and the Croissant Tasks
SHACL shapes (pyshacl).

## Publishing a version

`huggingface_hub` is not in the pixi environments; the upload scripts run with
`uv` and a logged-in Hub token (`hf auth login`).

```bash
# 1. Build and read the folder
pixi run -e full python scripts/build_hf_release.py synthetic_stalta
less build/hf/synthetic_stalta/README.md

# 2. Upload (dry run first); tags the Hub commit with the version
uv run --with huggingface_hub --with pyyaml python scripts/publish_hf_release.py synthetic_stalta
uv run --with huggingface_hub --with pyyaml python scripts/publish_hf_release.py synthetic_stalta --yes

# 3. Read the card on the Hub, then Settings -> "Generate DOI" (organization
#    admin). Record hf_revision and doi in datasets/releases.yaml. The Hub shows
#    the DOI in the dataset header; the card needs no new upload.
```

The DOI locks the repository: it cannot be deleted, renamed or made private
without a support request to Hugging Face. A new version gets "Generate new
DOI", which marks the previous DOI as outdated but keeps it resolving. That is
the persistence and tombstone behaviour the retirement policy needs, and it is
why the hidden repository never gets one: held-out partitions must stay
rotatable.

## Rules

- Only rows with split=validation and visibility=public leave the machine. The
  build runs with `REPERE_EVAL_DATA_DIR` pointed at an empty directory, refuses
  a suite whose private directory is not that one, and refuses if codameter
  loaded a hidden corpus. The upload re-checks every row and every hash.
- Third-party data keeps its terms. The synthetic STA/LTA release is MIT for
  Repère content and SCEDC terms for the waveform, with both SCEDC and CI
  network DOIs in the card.
- A changed row, scorer or recipe is a new version and a new DOI, never an
  edit in place.
