"""Host-vs-Docker parity for the STA/LTA sandbox (ROADMAP P2.2 acceptance).

This module exercises ``run_snippet`` end-to-end under both backends and
asserts that a deterministic snippet produces the same artefacts on the
host Python and inside the pinned Docker image. The CI workflow
``.github/workflows/sandbox-parity.yml`` runs the file twice — once
with ``FM_USE_DOCKER_SANDBOX=0`` and once with ``=1`` — but the parity
assertions themselves switch backends inside a single process so we
also catch drift on a developer's laptop.

Tests are gated on:

  - the ``[plot]`` and ``[geo]`` extras (numpy is enough for the simple
    snippet here, but obspy is exercised under Docker via the real image);
  - the ``docker`` binary being on PATH (only the docker leg is gated;
    the host-only test remains valid without it).
"""

from __future__ import annotations

import os
import shutil

import pytest

# Even the host leg needs numpy for the deterministic snippet, so gate
# the whole module on the [plot] extra rather than each test separately.
np = pytest.importorskip("numpy")

from frugalmind_suites.sta_lta.sandbox import (  # noqa: E402
    ENV_SANDBOX_IMAGE,
    ENV_USE_DOCKER,
    run_snippet,
)

_DETERMINISTIC_SNIPPET = """
import numpy as np

# Fixed seed → byte-identical artefacts across runs.
rng = np.random.default_rng(seed=20260511)
xs = rng.standard_normal(size=1024)

record(
    n=int(xs.size),
    mean=float(xs.mean()),
    std=float(xs.std()),
    sum=float(xs.sum()),
    # A handful of indexed values to detect any silent rounding drift
    # between numpy versions.
    head=[float(v) for v in xs[:5].tolist()],
)
print(f"computed {xs.size} samples")
"""


def _docker_available() -> bool:
    """``docker info`` works only when the daemon is reachable. ``which docker``
    on its own succeeds on machines where the CLI is installed but the daemon
    isn't — which would surface as a useless 'cannot connect' from inside
    every test. Probe daemon reachability cheaply here so the skip message
    is accurate."""
    if shutil.which("docker") is None:
        return False
    import subprocess

    try:
        rc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5.0,
        ).returncode
    except (subprocess.TimeoutExpired, OSError):
        return False
    return rc == 0


def _run_under(backend: str) -> dict:
    """Run the deterministic snippet under a given backend and return the
    captured ``record(...)`` artefacts."""
    original_use = os.environ.get(ENV_USE_DOCKER)
    original_image = os.environ.get(ENV_SANDBOX_IMAGE)
    try:
        if backend == "host":
            os.environ[ENV_USE_DOCKER] = "0"
        elif backend == "docker":
            os.environ[ENV_USE_DOCKER] = "1"
            # Allow the CI workflow / developer to override the tag via env;
            # default falls through to DEFAULT_SANDBOX_IMAGE in sandbox.py.
        else:
            raise ValueError(backend)

        result = run_snippet(_DETERMINISTIC_SNIPPET, timeout_s=60.0)
    finally:
        if original_use is None:
            os.environ.pop(ENV_USE_DOCKER, None)
        else:
            os.environ[ENV_USE_DOCKER] = original_use
        if original_image is None:
            os.environ.pop(ENV_SANDBOX_IMAGE, None)
        else:
            os.environ[ENV_SANDBOX_IMAGE] = original_image
    assert result.ok, f"{backend} backend failed: {result.stderr}"
    return result.artifacts


# ---------------------------------------------------------------------------
# Host-only baseline — always runs, even without Docker on the box
# ---------------------------------------------------------------------------


def test_host_backend_produces_expected_deterministic_artefacts():
    """If this fails, the snippet itself is non-deterministic — fix that
    before debugging the docker parity test."""
    artefacts = _run_under("host")
    assert artefacts["n"] == 1024
    assert len(artefacts["head"]) == 5
    # numpy is pinned in the docker image; we don't pin it on the host CI
    # runner, so we accept tiny float drift here. Tighten on docker only.
    assert abs(artefacts["mean"]) < 1.0


# ---------------------------------------------------------------------------
# Docker leg — gated on the daemon being reachable
# ---------------------------------------------------------------------------


pytestmark_docker = pytest.mark.skipif(
    not _docker_available(),
    reason=(
        "docker daemon not reachable; this leg only runs in CI's sandbox-parity"
        " workflow or on a developer machine with docker started"
    ),
)


@pytestmark_docker
def test_docker_backend_produces_artefacts_matching_host():
    """The point of the pinned image: identical bits in, identical
    artefacts out. The seeded numpy RNG is the cleanest deterministic
    probe — if obspy/scikit-image differ, this test won't catch it
    (the canonical plot recipe drift tests will), but if the *Python
    bytes* differ between backends, this fails first."""
    host_art = _run_under("host")
    docker_art = _run_under("docker")

    # n / head / sum must agree exactly: integer count, list of floats,
    # and a sum that's a single deterministic float.
    assert host_art["n"] == docker_art["n"]
    assert host_art["head"] == docker_art["head"]
    assert host_art["sum"] == docker_art["sum"], (
        f"deterministic snippet diverged between backends — "
        f"host={host_art['sum']!r} docker={docker_art['sum']!r}. "
        "Likely cause: numpy version drift between host and pinned image."
    )
    assert host_art["mean"] == docker_art["mean"]
    assert host_art["std"] == docker_art["std"]
