"""Code-execution sandbox for STA/LTA suite scoring.

This is a robustness boundary, not a security boundary. It uses subprocesses,
timeouts, and structured artifact capture so one bad model response does not
break an evaluation run.

Two execution backends share the same surface (P2.2):

* **Host Python** (default). Snippets run under ``sys.executable`` against
  whatever the host has installed. Fast, deterministic on a given machine,
  but vulnerable to "works on my machine" drift across contributors.
* **Docker image** (opt-in via ``FM_USE_DOCKER_SANDBOX=1``). Snippets run
  inside the pinned ``docker/sandbox.Dockerfile`` image. Reproducible
  across machines, at the cost of needing Docker on the host. The image
  name is configurable via ``FM_SANDBOX_IMAGE``
  (default ``ghcr.io/mdenolle/repere-sandbox:latest``).

Both backends return identical :class:`ExecResult` shapes and use the
same ``_PREAMBLE`` so ``record(**kwargs)`` artefact capture works the same
way in either mode.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Env-var contract for the docker backend. Names live here so tests can
# reference them without hard-coding strings, and so the docker workflow
# in CI is documented next to the dispatch.
ENV_USE_DOCKER = "FM_USE_DOCKER_SANDBOX"
ENV_SANDBOX_IMAGE = "FM_SANDBOX_IMAGE"
DEFAULT_SANDBOX_IMAGE = "ghcr.io/mdenolle/repere-sandbox:latest"


@dataclass
class ExecResult:
    """Outcome of running model-generated code in the sandbox."""

    ok: bool
    stdout: str
    stderr: str
    returncode: int | None
    timed_out: bool
    artifacts: dict[str, Any]
    artifact_files: list[str]


_CODE_FENCE = re.compile(r"```(?:python|py)?\n(.*?)```", re.DOTALL)


def extract_code(model_output: str) -> str:
    """Pull Python code out of a model response."""
    matches = _CODE_FENCE.findall(model_output)
    if matches:
        return max(matches, key=len).strip()
    if any(tok in model_output for tok in ("import ", "def ", "from ")):
        return model_output.strip()
    return ""


_PREAMBLE = textwrap.dedent(
    """
    import json, os, sys, traceback
    OUT_DIR = os.environ["FM_OUT_DIR"]
    _result_path = os.path.join(OUT_DIR, "__fm_result__.json")
    _captured = {}

    def record(**kwargs):
        _captured.update(kwargs)

    def _write_result():
        safe = {}
        for k, v in _captured.items():
            try:
                json.dumps(v)
                safe[k] = v
            except Exception:
                safe[k] = repr(v)
        with open(_result_path, "w") as f:
            json.dump(safe, f)

    import atexit
    atexit.register(_write_result)
    """
)


def _persist_artifacts(
    out_dir: str, skip_names: frozenset[str] = frozenset()
) -> tuple[dict[str, Any], list[str]]:
    """Collect the ``record(...)`` artefact dict and any non-internal files
    produced by the snippet, copying the files to a separate tmpdir so they
    survive the ``out_dir`` cleanup. Shared between host and docker paths.
    ``skip_names`` lists staged input files that must not be reported as
    artefacts (RCA suite, ``input_files``)."""
    result_file = Path(out_dir) / "__fm_result__.json"
    artifacts: dict[str, Any] = {}
    if result_file.exists():
        try:
            artifacts = json.loads(result_file.read_text())
        except Exception:
            pass

    # Restrict to regular files. A snippet that calls ``os.makedirs`` or
    # writes a FIFO would otherwise trip ``read_bytes()`` with
    # IsADirectoryError / OSError and abort the run. We accept symlinks
    # too — Path.is_file() resolves them — but skip anything that isn't
    # a plain file the caller can later open and read.
    artifact_files: list[str] = []
    for path in Path(out_dir).iterdir():
        if path.name in ("snippet.py", "__fm_result__.json") or path.name in skip_names:
            continue
        if not path.is_file():
            continue
        artifact_files.append(str(path))

    if artifact_files:
        persist_dir = Path(tempfile.mkdtemp(prefix="fm_artifacts_"))
        kept: list[str] = []
        for artifact_file in artifact_files:
            src = Path(artifact_file)
            dst = persist_dir / src.name
            try:
                dst.write_bytes(src.read_bytes())
            except OSError:
                # A vanishingly rare race (file unlinked between iterdir
                # and read) or unreadable file shouldn't sink the whole
                # eval. Skip and move on; the scorer sees what survived.
                continue
            kept.append(str(dst))
        artifact_files = kept
    return artifacts, artifact_files


def _stage_inputs(out_dir: str, input_files: dict[str, str] | None) -> frozenset[str]:
    """Copy ``{name: host_path}`` into ``out_dir`` so the snippet sees them in
    its working directory (host backend) or under ``/work`` (docker backend).
    Returns the staged basenames so artefact collection can skip them."""
    if not input_files:
        return frozenset()
    staged: set[str] = set()
    for name, src in input_files.items():
        base = Path(name).name  # never allow a path to escape out_dir
        dst = Path(out_dir) / base
        dst.write_bytes(Path(src).read_bytes())
        staged.add(base)
    return frozenset(staged)


def _run_snippet_host(
    code: str,
    *,
    timeout_s: float,
    extra_env: dict[str, str] | None,
    input_files: dict[str, str] | None = None,
) -> ExecResult:
    """Execute the snippet under the host's ``sys.executable``."""
    with tempfile.TemporaryDirectory(prefix="fm_sta_lta_") as out_dir:
        snippet_path = Path(out_dir) / "snippet.py"
        snippet_path.write_text(_PREAMBLE + "\n" + code)
        staged = _stage_inputs(out_dir, input_files)

        env = {"FM_OUT_DIR": out_dir, "PATH": "/usr/bin:/bin"}
        if extra_env:
            env.update(extra_env)
        for key in ("HOME", "TMPDIR", "PYTHONPATH"):
            if key in os.environ:
                env[key] = os.environ[key]

        try:
            proc = subprocess.run(
                [sys.executable, str(snippet_path)],
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env=env,
                cwd=out_dir,
            )
            timed_out = False
            stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as e:
            timed_out = True
            stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr_raw = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
            stderr = stderr_raw + f"\n[TIMEOUT after {timeout_s}s]"
            rc = None

        artifacts, artifact_files = _persist_artifacts(out_dir, staged)
        return ExecResult(
            ok=(rc == 0 and not timed_out),
            stdout=stdout,
            stderr=stderr,
            returncode=rc,
            timed_out=timed_out,
            artifacts=artifacts,
            artifact_files=artifact_files,
        )


def _run_snippet_docker(
    code: str,
    *,
    timeout_s: float,
    extra_env: dict[str, str] | None,
    image: str,
    input_files: dict[str, str] | None = None,
) -> ExecResult:
    """Execute the snippet inside the pinned Docker sandbox image.

    Mounts a host tmpdir at /work inside the container, writes the snippet
    + preamble there, and runs ``python /work/snippet.py``. The container's
    FM_OUT_DIR is /work, so the artefact-capture preamble lands the result
    JSON and any plot files in the same host directory that
    ``_persist_artifacts`` reads after the run.

    A missing ``docker`` binary surfaces as ``ok=False`` with a structured
    error rather than an exception, matching the agent-tools convention.
    """
    docker_bin = shutil.which("docker")
    if docker_bin is None:
        return ExecResult(
            ok=False,
            stdout="",
            stderr=(
                "docker binary not found on PATH; "
                f"unset {ENV_USE_DOCKER} to fall back to the host Python sandbox"
            ),
            returncode=None,
            timed_out=False,
            artifacts={},
            artifact_files=[],
        )

    with tempfile.TemporaryDirectory(prefix="fm_sta_lta_") as out_dir:
        snippet_path = Path(out_dir) / "snippet.py"
        snippet_path.write_text(_PREAMBLE + "\n" + code)
        staged = _stage_inputs(out_dir, input_files)
        # ``tempfile.TemporaryDirectory`` ships at mode 0700 owned by the
        # host UID. The container runs as a non-root ``fmuser`` whose UID
        # almost never matches the host's, so the default permissions
        # would prevent the container from reading snippet.py or writing
        # back the result JSON. The cleanest fix is to ask docker to run
        # the container with the host's UID/GID — then the bind-mount
        # ACLs line up and the existing 0700 is enough. Falls back
        # gracefully on platforms without ``os.geteuid`` (Windows): we
        # let the container run with its built-in uid and rely on the
        # tmpdir's group/other bits, which are already loose enough on
        # those platforms.
        host_uid_gid: str | None = None
        if hasattr(os, "geteuid") and hasattr(os, "getegid"):
            host_uid_gid = f"{os.geteuid()}:{os.getegid()}"

        cmd: list[str] = [
            docker_bin,
            "run",
            "--rm",
            "--network=none",  # snippets shouldn't reach out; FDSN happens via the agent tool
        ]
        if host_uid_gid is not None:
            cmd.extend(["--user", host_uid_gid])
        cmd.extend(
            [
                "-v",
                f"{out_dir}:/work",
                "-e",
                "FM_OUT_DIR=/work",
                # HOME inside the container would be /home/fmuser, which a
                # foreign-UID process can't write. Point it at /tmp so any
                # numpy / matplotlib caches that try to scribble to $HOME
                # don't crash the run.
                "-e",
                "HOME=/tmp",
            ]
        )
        if extra_env:
            for k, v in extra_env.items():
                cmd.extend(["-e", f"{k}={v}"])
        cmd.extend([image, "python", "/work/snippet.py"])

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=out_dir,
            )
            timed_out = False
            stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as e:
            timed_out = True
            stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr_raw = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
            stderr = stderr_raw + f"\n[TIMEOUT after {timeout_s}s (docker)]"
            rc = None

        artifacts, artifact_files = _persist_artifacts(out_dir, staged)
        return ExecResult(
            ok=(rc == 0 and not timed_out),
            stdout=stdout,
            stderr=stderr,
            returncode=rc,
            timed_out=timed_out,
            artifacts=artifacts,
            artifact_files=artifact_files,
        )


def _docker_requested() -> bool:
    """Read ``FM_USE_DOCKER_SANDBOX`` and treat the standard truthy spellings
    as 'use docker'. Anything else (unset, '0', 'false', '') stays on the
    host Python backend so the default behaviour is unchanged."""
    raw = os.environ.get(ENV_USE_DOCKER, "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def run_snippet(
    code: str,
    *,
    timeout_s: float = 30.0,
    extra_env: dict[str, str] | None = None,
    image: str | None = None,
    input_files: dict[str, str] | None = None,
) -> ExecResult:
    """Execute a Python snippet in a fresh subprocess with a timeout.

    The backend is chosen by environment variable:

    * ``FM_USE_DOCKER_SANDBOX`` truthy → pinned Docker image (P2.2).
    * Anything else → host Python (the historical behaviour).

    When the docker backend is active, the image is resolved in priority order:
    the explicit ``image`` argument (a per-suite image — e.g. a seisbench or
    noisepy sandbox for numerical-regression tasks), then ``FM_SANDBOX_IMAGE``,
    then :data:`DEFAULT_SANDBOX_IMAGE`. The host backend ignores ``image``.

    ``input_files`` (``{basename: host_path}``) are copied into the snippet's
    working directory before execution and are excluded from the returned
    ``artifact_files``. Added for the RCA suite (shape B ``inputs.files``);
    default ``None`` leaves the historical behaviour unchanged.
    """
    if not code.strip():
        return ExecResult(False, "", "empty code", None, False, {}, [])

    # Only forward ``input_files`` when the caller supplied it, so the
    # historical call signature (and every existing test double) is unchanged
    # for callers that don't stage inputs.
    extra: dict[str, Any] = {"input_files": input_files} if input_files else {}
    if _docker_requested():
        resolved = image or os.environ.get(ENV_SANDBOX_IMAGE) or DEFAULT_SANDBOX_IMAGE
        return _run_snippet_docker(
            code,
            timeout_s=timeout_s,
            extra_env=extra_env,
            image=resolved,
            **extra,
        )
    return _run_snippet_host(code, timeout_s=timeout_s, extra_env=extra_env, **extra)
