# FrugalMind sandbox image

A pinned execution environment for the STA/LTA suite scorers and the
ReAct agent's `python_session` tool. Same Python, same library versions
across every contributor's machine and CI.

## Build locally

From the repo root:

```bash
docker build -f docker/sandbox.Dockerfile -t frugalmind-sandbox:dev .
```

The build is single-stage and finishes in ~2 minutes on a cold cache,
~10 seconds on a warm one. Final image size is ~700 MB (driven by
numpy + scipy + matplotlib + obspy + scikit-image).

## Run the sandbox path locally

The host-Python sandbox is the default. Opt into the Docker sandbox
with one env var:

```bash
FM_USE_DOCKER_SANDBOX=1 FM_SANDBOX_IMAGE=frugalmind-sandbox:dev pytest
```

`FM_SANDBOX_IMAGE` defaults to `ghcr.io/mdenolle/frugalmind-sandbox:latest`
once the CI workflow has pushed an image.

## Pinned versions

| Library | Pin | Why pinned here |
| --- | --- | --- |
| Python | 3.10 (slim-bookworm) | Matches the project's test target. |
| numpy | 1.26.4 | Held below 2.0 — obspy 1.4.1 hasn't declared numpy 2 compatibility, and bumping silently changes float-printing in plot golden text. |
| scipy | 1.13.1 | Last release with broad obspy compatibility before the FFT API churn. |
| matplotlib | 3.9.2 | Backend pinned via `MPLBACKEND=Agg` env. |
| scikit-image | 0.24.0 | SSIM API stable since 0.20; this is the last release with the public-API helpers used by the plot scorer. |
| obspy | 1.4.1 | Current stable. |
| PyYAML | 6.0.2 | Stable. |

When you bump any of these, regenerate the plot goldens
(`python scripts/build_plot_goldens.py`) and verify the drift tests
still pass against the committed PNGs.

## CI

`.github/workflows/sandbox-image.yml` builds the image on every PR and
pushes to GHCR (`ghcr.io/mdenolle/frugalmind-sandbox`) on tag pushes
and merges to `main`. `.github/workflows/sandbox-parity.yml` runs the
relevant test set twice — once with `FM_USE_DOCKER_SANDBOX=0` (host
Python), once with `FM_USE_DOCKER_SANDBOX=1` against the locally-built
`frugalmind-sandbox:ci` tag — and the dual-job matches the ROADMAP P2.2
acceptance criterion. The pre-existing `.github/workflows/evals.yml`
runs Pixi smoke tests and is unrelated to the sandbox parity flow.
