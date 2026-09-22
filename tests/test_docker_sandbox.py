"""Dispatch contracts for the Docker sandbox backend (ROADMAP P2.2).

These tests don't require Docker to be installed. They verify the
*dispatch logic* in :mod:`repere_suites.sta_lta.sandbox` — which
backend is chosen, how env vars are parsed, and what happens when the
``docker`` binary is missing. The host-Python backend itself is already
covered by ``tests/test_sta_lta_suite.py``; the actual docker round-trip
(image build + run) is covered by ``tests/test_sandbox_parity.py`` and
gated on Docker availability.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from repere_suites.sta_lta import sandbox
from repere_suites.sta_lta.sandbox import (
    DEFAULT_SANDBOX_IMAGE,
    ENV_SANDBOX_IMAGE,
    ENV_USE_DOCKER,
    ExecResult,
    _docker_requested,
    run_snippet,
)

# ---------------------------------------------------------------------------
# 1. Env-var parsing — _docker_requested
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1", True),
        ("true", True),
        ("True", True),
        ("yes", True),
        ("on", True),
        (" 1 ", True),  # whitespace tolerated
        ("0", False),
        ("false", False),
        ("", False),
        ("no", False),
        ("off", False),
        ("foo", False),  # unknown spellings stay on host backend
    ],
)
def test_docker_requested_recognises_truthy_spellings(monkeypatch, value, expected):
    monkeypatch.setenv(ENV_USE_DOCKER, value)
    assert _docker_requested() is expected


def test_docker_requested_defaults_to_false_when_unset(monkeypatch):
    """Default behaviour must remain host-Python — no opt-out required."""
    monkeypatch.delenv(ENV_USE_DOCKER, raising=False)
    assert _docker_requested() is False


# ---------------------------------------------------------------------------
# 2. Dispatch routing — run_snippet picks the right backend
# ---------------------------------------------------------------------------


def test_run_snippet_uses_host_backend_by_default(monkeypatch):
    """With FM_USE_DOCKER_SANDBOX unset, the host backend handles the call.

    We patch _run_snippet_host to a sentinel and assert it was the one invoked.
    """
    monkeypatch.delenv(ENV_USE_DOCKER, raising=False)
    calls: list[str] = []

    def fake_host(code, *, timeout_s, extra_env):
        calls.append("host")
        return ExecResult(True, "host-out", "", 0, False, {}, [])

    def fake_docker(code, *, timeout_s, extra_env, image):
        calls.append(f"docker:{image}")
        return ExecResult(True, "docker-out", "", 0, False, {}, [])

    monkeypatch.setattr(sandbox, "_run_snippet_host", fake_host)
    monkeypatch.setattr(sandbox, "_run_snippet_docker", fake_docker)
    result = run_snippet("print('hi')", timeout_s=1.0)
    assert calls == ["host"]
    assert result.stdout == "host-out"


def test_run_snippet_dispatches_to_docker_when_env_set(monkeypatch):
    monkeypatch.setenv(ENV_USE_DOCKER, "1")
    monkeypatch.delenv(ENV_SANDBOX_IMAGE, raising=False)
    calls: list[str] = []

    def fake_host(code, *, timeout_s, extra_env):
        calls.append("host")
        return ExecResult(True, "", "", 0, False, {}, [])

    def fake_docker(code, *, timeout_s, extra_env, image):
        calls.append(f"docker:{image}")
        return ExecResult(True, "", "", 0, False, {}, [])

    monkeypatch.setattr(sandbox, "_run_snippet_host", fake_host)
    monkeypatch.setattr(sandbox, "_run_snippet_docker", fake_docker)
    run_snippet("print('hi')", timeout_s=1.0)
    # Default image when FM_SANDBOX_IMAGE is unset.
    assert calls == [f"docker:{DEFAULT_SANDBOX_IMAGE}"]


def test_run_snippet_honours_custom_image_tag(monkeypatch):
    monkeypatch.setenv(ENV_USE_DOCKER, "1")
    monkeypatch.setenv(ENV_SANDBOX_IMAGE, "repere-sandbox:dev")
    seen: dict[str, str] = {}

    def fake_docker(code, *, timeout_s, extra_env, image):
        seen["image"] = image
        return ExecResult(True, "", "", 0, False, {}, [])

    monkeypatch.setattr(sandbox, "_run_snippet_docker", fake_docker)
    run_snippet("print('hi')", timeout_s=1.0)
    assert seen["image"] == "repere-sandbox:dev"


def test_empty_code_short_circuits_before_dispatch(monkeypatch):
    """Empty snippets must not pay the cost of a docker run (nor a host fork)."""
    monkeypatch.setenv(ENV_USE_DOCKER, "1")
    calls: list[str] = []

    def fake_host(*a, **kw):
        calls.append("host")
        return ExecResult(True, "", "", 0, False, {}, [])

    def fake_docker(*a, **kw):
        calls.append("docker")
        return ExecResult(True, "", "", 0, False, {}, [])

    monkeypatch.setattr(sandbox, "_run_snippet_host", fake_host)
    monkeypatch.setattr(sandbox, "_run_snippet_docker", fake_docker)
    result = run_snippet("   ", timeout_s=1.0)
    assert calls == []
    assert result.ok is False
    assert result.stderr == "empty code"


# ---------------------------------------------------------------------------
# 3. Missing docker binary — returns structured error, never raises
# ---------------------------------------------------------------------------


def test_docker_backend_returns_structured_error_when_binary_missing(monkeypatch):
    """If FM_USE_DOCKER_SANDBOX is set but no docker on PATH, surface an
    informative ok=False rather than letting an OSError bubble up. The
    error message must mention the env var name so the user can recover."""
    monkeypatch.setenv(ENV_USE_DOCKER, "1")
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: None)

    result = run_snippet("print('hi')", timeout_s=1.0)
    assert result.ok is False
    assert result.returncode is None
    assert result.timed_out is False
    assert "docker" in result.stderr.lower()
    assert ENV_USE_DOCKER in result.stderr


# ---------------------------------------------------------------------------
# 4. Docker command construction — verify the cmd shape via subprocess.run mock
# ---------------------------------------------------------------------------


def _capture_subprocess_run(monkeypatch):
    """Replace subprocess.run with a recorder that returns a successful proc.

    Returns the list the recorder appends to so the test can inspect the
    constructed argv.
    """
    captured: list[list[str]] = []

    class _FakeProc:
        def __init__(self):
            self.stdout = ""
            self.stderr = ""
            self.returncode = 0

    def fake_run(cmd, **kwargs):
        captured.append(list(cmd))
        return _FakeProc()

    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    return captured


def test_docker_command_includes_image_and_volume_and_env(monkeypatch):
    """The docker invocation must mount the host tmpdir at /work, set
    FM_OUT_DIR=/work, run as --rm, and pass the configured image last
    before the in-container `python /work/snippet.py`. Any drift here
    breaks the artefact-capture contract with the preamble."""
    monkeypatch.setenv(ENV_USE_DOCKER, "1")
    monkeypatch.setenv(ENV_SANDBOX_IMAGE, "repere-sandbox:probe")
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: "/usr/bin/docker")
    captured = _capture_subprocess_run(monkeypatch)

    run_snippet("print('hi')", timeout_s=2.0)
    assert len(captured) == 1
    cmd = captured[0]
    assert cmd[0] == "/usr/bin/docker"
    assert cmd[1:3] == ["run", "--rm"]
    assert "--network=none" in cmd
    # Volume mount: -v <hosttmp>:/work
    vol_idx = cmd.index("-v")
    assert cmd[vol_idx + 1].endswith(":/work"), cmd[vol_idx + 1]
    # FM_OUT_DIR env: -e FM_OUT_DIR=/work
    env_idx = cmd.index("-e")
    assert "FM_OUT_DIR=/work" in [cmd[env_idx + 1], *cmd[env_idx + 3 :: 2]]
    # Image then in-container python invocation.
    assert cmd[-3] == "repere-sandbox:probe"
    assert cmd[-2:] == ["python", "/work/snippet.py"]


def test_docker_command_passes_extra_env_through(monkeypatch):
    """extra_env entries must arrive in the container as `-e KEY=VALUE`."""
    monkeypatch.setenv(ENV_USE_DOCKER, "1")
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: "/usr/bin/docker")
    captured = _capture_subprocess_run(monkeypatch)

    run_snippet("print('hi')", timeout_s=2.0, extra_env={"FM_PROBE": "abc"})
    cmd = captured[0]
    # Find the FM_PROBE entry; it must follow a `-e` flag.
    indices = [i for i, x in enumerate(cmd) if x == "FM_PROBE=abc"]
    assert indices, cmd
    assert cmd[indices[0] - 1] == "-e"


def test_docker_timeout_returns_timed_out_result(monkeypatch):
    """When subprocess.run raises TimeoutExpired, the docker backend
    surfaces ok=False with timed_out=True — same contract as the host
    backend, so downstream callers don't have to special-case."""
    monkeypatch.setenv(ENV_USE_DOCKER, "1")
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: "/usr/bin/docker")

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 1.0))

    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    result = run_snippet("print('hi')", timeout_s=0.1)
    assert result.ok is False
    assert result.timed_out is True
    assert result.returncode is None
    assert "TIMEOUT" in result.stderr


# ---------------------------------------------------------------------------
# 5. ExecResult shape stays identical across backends
# ---------------------------------------------------------------------------


def test_host_and_docker_both_produce_exec_result_instances(monkeypatch):
    """Trivially via mocks — but the assertion documents the contract:
    both backends produce :class:`ExecResult`, callers can polymorphically
    consume the output without checking which path was taken."""
    monkeypatch.setattr(
        sandbox,
        "_run_snippet_host",
        lambda code, *, timeout_s, extra_env: ExecResult(True, "h", "", 0, False, {}, []),
    )
    monkeypatch.setattr(
        sandbox,
        "_run_snippet_docker",
        lambda code, *, timeout_s, extra_env, image: ExecResult(
            True, "d", "", 0, False, {}, []
        ),
    )
    monkeypatch.delenv(ENV_USE_DOCKER, raising=False)
    assert isinstance(run_snippet("x=1", timeout_s=1.0), ExecResult)

    monkeypatch.setenv(ENV_USE_DOCKER, "1")
    assert isinstance(run_snippet("x=1", timeout_s=1.0), ExecResult)


# ---------------------------------------------------------------------------
# 6. Round-trip via run_snippet (host backend only — proves the refactor
#    didn't break the existing path).
# ---------------------------------------------------------------------------


def test_run_snippet_host_backend_round_trips_record_call(monkeypatch):
    """The historical sandbox contract: stdout flows through, `record(...)`
    artefacts end up in result.artifacts. Pin it explicitly so future
    refactors of the dispatch can't silently regress."""
    monkeypatch.delenv(ENV_USE_DOCKER, raising=False)
    result = run_snippet(
        "record(answer=42)\nprint('ok')",
        timeout_s=15.0,
    )
    assert result.ok is True
    assert "ok" in result.stdout
    assert result.artifacts == {"answer": 42}


# ---------------------------------------------------------------------------
# 7. _persist_artifacts is robust to subdirectories and unreadable files
# ---------------------------------------------------------------------------


def test_persist_artifacts_skips_subdirectories_without_raising(tmp_path, monkeypatch):
    """A snippet that calls ``os.makedirs`` (or any code that creates a
    directory in FM_OUT_DIR) would have tripped the original implementation
    with IsADirectoryError when read_bytes hit the subdir. We now filter
    non-regular files first and skip them silently — the scorer sees
    whatever regular files survived."""
    # Build a fake out_dir matching the convention in the production code:
    # snippet.py + __fm_result__.json are dropped, and we add one regular
    # file (should be persisted) plus one subdirectory (should be skipped).
    out_dir = tmp_path
    (out_dir / "snippet.py").write_text("# internal")
    (out_dir / "__fm_result__.json").write_text(json.dumps({"k": "v"}))
    (out_dir / "plot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (out_dir / "scratch").mkdir()
    (out_dir / "scratch" / "inner.txt").write_text("should not be persisted")

    artifacts, artifact_files = sandbox._persist_artifacts(str(out_dir))
    assert artifacts == {"k": "v"}, "result JSON must still be parsed"
    # Exactly one survivor: plot.png. No subdirs, no inner files.
    persisted_names = sorted(Path(p).name for p in artifact_files)
    assert persisted_names == ["plot.png"]
    # And the persisted file is readable, with the bytes we wrote.
    assert Path(artifact_files[0]).read_bytes().startswith(b"\x89PNG")


def test_persist_artifacts_returns_empty_when_only_internal_files_present(tmp_path):
    """When nothing but snippet.py + __fm_result__.json are present (the
    common case), the function returns an empty artifact_files list and
    does not allocate a persist_dir."""
    (tmp_path / "snippet.py").write_text("# internal")
    (tmp_path / "__fm_result__.json").write_text(json.dumps({}))
    artifacts, artifact_files = sandbox._persist_artifacts(str(tmp_path))
    assert artifacts == {}
    assert artifact_files == []


# ---------------------------------------------------------------------------
# 8. Docker command construction — verify the --user UID mapping
# ---------------------------------------------------------------------------


def test_docker_command_includes_user_uid_gid_when_available(monkeypatch):
    """The container runs as a non-root fmuser whose UID rarely matches
    the host's. Without --user, the bind-mounted tmpdir (mode 0700, host
    UID) is unreadable from inside the container. We pin that --user
    pairs the container with the host's UID:GID — and on Windows (no
    os.geteuid), we don't pass --user at all."""
    monkeypatch.setenv(ENV_USE_DOCKER, "1")
    monkeypatch.setenv(ENV_SANDBOX_IMAGE, "repere-sandbox:probe")
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: "/usr/bin/docker")
    # Fake geteuid/getegid to known values so the assertion is deterministic.
    monkeypatch.setattr(sandbox.os, "geteuid", lambda: 1729)
    monkeypatch.setattr(sandbox.os, "getegid", lambda: 4242)
    captured = _capture_subprocess_run(monkeypatch)

    run_snippet("print('hi')", timeout_s=2.0)
    cmd = captured[0]
    assert "--user" in cmd, cmd
    user_idx = cmd.index("--user")
    assert cmd[user_idx + 1] == "1729:4242"
    # HOME=/tmp must be set too, so foreign-UID processes don't try to
    # scribble to /home/fmuser (which they can't write).
    home_envs = [cmd[i + 1] for i, x in enumerate(cmd) if x == "-e"]
    assert "HOME=/tmp" in home_envs


def test_docker_command_omits_user_flag_when_os_has_no_geteuid(monkeypatch):
    """On Windows hosts ``os.geteuid`` doesn't exist. The dispatch must
    skip the --user flag rather than crash with AttributeError, and let
    the container run with its built-in UID."""
    monkeypatch.setenv(ENV_USE_DOCKER, "1")
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.delattr(sandbox.os, "geteuid", raising=False)
    captured = _capture_subprocess_run(monkeypatch)

    run_snippet("print('hi')", timeout_s=2.0)
    cmd = captured[0]
    assert "--user" not in cmd, cmd
