# Repère STA/LTA sandbox image
#
# A single, pinned execution environment for the STA/LTA suite scorers
# and the ReAct agent's `python_session` tool. Same Python, same library
# versions across every contributor's machine and CI.
#
# Pins match the project's optional extras (`[geo]`, `[plot]`) and the
# versions tested against the canonical plot goldens (`recipe.py`).
# If you bump a pin here, regenerate the goldens with
# `python scripts/build_plot_goldens.py` and check the drift tests still
# pass against the old PNGs (small numerical differences will show up as
# SSIM regressions).
#
# Build locally:
#   docker build -f docker/sandbox.Dockerfile -t repere-sandbox:dev .
#
# Run a snippet end-to-end (host-side path is the same as
# REPERE_USE_DOCKER_SANDBOX=1 in sandbox.py):
#   docker run --rm -v "$(pwd)/scratch:/work" -e REPERE_OUT_DIR=/work \
#     repere-sandbox:dev python /work/snippet.py
#
# Published to ghcr.io/mdenolle/repere-sandbox on tag pushes by
# .github/workflows/sandbox-image.yml.

FROM python:3.10-slim-bookworm

# Non-interactive apt; deterministic pip; no pyc churn in layers.
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLBACKEND=Agg

# Minimal system deps for the scientific stack:
#   - libgomp1   : OpenMP runtime, used by numpy / scikit-image
#   - libgl1     : libGL.so.1, pulled by matplotlib on some plotting paths
#   - libglib2.0 : transitively required by libgl1
#   - tini       : PID-1 reaper so docker run --rm exits cleanly on timeout
#   - ca-certificates : HTTPS for any pip / FDSN call inside the sandbox
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libgomp1 \
        libgl1 \
        libglib2.0-0 \
        tini \
        ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Pinned scientific stack.
#
# numpy is held below 2.0 because obspy 1.4.1 doesn't yet declare
# numpy>=2 compatibility — bumping to numpy 2.x silently changes
# float-printing in plot golden text and trips SSIM regressions.
# When obspy ships a 2.0-compatible release, lift the pin together.
RUN pip install --no-cache-dir \
        "numpy==1.26.4" \
        "scipy==1.13.1" \
        "matplotlib==3.9.2" \
        "scikit-image==0.24.0" \
        "obspy==1.4.1" \
        "PyYAML==6.0.2"

# Run as non-root. The host-side `run_snippet` driver mounts a writable
# tmpdir at /work and sets REPERE_OUT_DIR=/work, so the container only needs
# write access there.
RUN useradd --create-home --shell /bin/bash fmuser \
 && mkdir -p /work \
 && chown fmuser:fmuser /work
USER fmuser
WORKDIR /work

# tini gives us proper signal handling so a host-side
# `subprocess.run(..., timeout=...)` kill terminates the snippet cleanly
# rather than leaving an orphan Python interpreter behind.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "--version"]
