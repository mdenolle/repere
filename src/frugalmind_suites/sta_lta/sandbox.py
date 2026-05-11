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
  (default ``ghcr.io/mdenolle/frugalmind-sandbox:latest``).

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
DEFAULT_SANDBOX_IMAGE = "ghcr.io/mdenolle/frugalmind-sandbox:latest"


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


def _persist_artifacts(out_dir: str) -> tuple[dict[str, Any], list[str]]:
    """Collect the ``record(...)`` artefact dict and any non-internal files
    produced by the snippet, copying the files to a separate tmpdir so they
    survive the ``out_dir`` cleanup. Shared between host and docker paths."""
    result_file = Path(out_dir) / "__fm_result__.json"
    artifacts: dict[str, Any] = {}
    if result_file.exists():
        try:
            artifacts = json.loads(result_file.read_text())
        except Exception:
            pass

    artifact_files = [
        str(path)
        for path in Path(out_dir).iterdir()
        if path.name not in ("snippet.py", "__fm_result__.json")
    ]
    if artifact_files:
        persist_dir = Path(tempfile.mkdtemp(prefix="fm_artifacts_"))
        kept: list[str] = []
        for artifact_file in artifact_files:
            src = Path(artifact_file)
            dst = persist_dir / src.name
            dst.write_bytes(src.read_bytes())
            kept.append(str(dst))
        artifact_files = kept
    return artifacts, artifact_files


def _run_snippet_host(
    code: str,
    *,
    timeout_s: float,
    extra_env: dict[str, str] | None,
) -> ExecResult:
    """Execute the snippet under the host's ``sys.executable``."""
    with tempfile.TemporaryDirectory(prefix="fm_sta_lta_") as out_dir:
        snippet_path = Path(out_dir) / "snippet.py"
        snippet_path.write_text(_PREAMBLE + "\n" + code)

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

        artifacts, artifact_files = _persist_artifacts(out_dir)
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

        cmd: list[str] = [
            docker_bin,
            "run",
            "--rm",
            "--network=none",  # snippets shouldn't reach out; FDSN happens via the agent tool
            "-v",
            f"{out_dir}:/work",
            "-e",
            "FM_OUT_DIR=/work",
        ]
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

        artifacts, artifact_files = _persist_artifacts(out_dir)
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
) -> ExecResult:
    """Execute a Python snippet in a fresh subprocess with a timeout.

    The backend is chosen by environment variable:

    * ``FM_USE_DOCKER_SANDBOX`` truthy → pinned Docker image (P2.2).
      Image name from ``FM_SANDBOX_IMAGE`` (default
      ``ghcr.io/mdenolle/frugalmind-sandbox:latest``).
    * Anything else → host Python (the historical behaviour).
    """
    if not code.strip():
        return ExecResult(False, "", "empty code", None, False, {}, [])

    if _docker_requested():
        image = os.environ.get(ENV_SANDBOX_IMAGE) or DEFAULT_SANDBOX_IMAGE
        return _run_snippet_docker(
            code,
            timeout_s=timeout_s,
            extra_env=extra_env,
            image=image,
        )
    return _run_snippet_host(code, timeout_s=timeout_s, extra_env=extra_env)
