"""Code-execution sandbox for STA/LTA suite scoring.

This is a robustness boundary, not a security boundary. It uses subprocesses,
timeouts, and structured artifact capture so one bad model response does not
break an evaluation run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import json
import re
import subprocess
import sys
import tempfile
import textwrap


@dataclass
class ExecResult:
    """Outcome of running model-generated code in the sandbox."""

    ok: bool
    stdout: str
    stderr: str
    returncode: Optional[int]
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


def run_snippet(
    code: str,
    *,
    timeout_s: float = 30.0,
    extra_env: Optional[dict[str, str]] = None,
) -> ExecResult:
    """Execute a Python snippet in a fresh subprocess with a timeout."""
    if not code.strip():
        return ExecResult(False, "", "empty code", None, False, {}, [])

    with tempfile.TemporaryDirectory(prefix="fm_sta_lta_") as out_dir:
        snippet_path = Path(out_dir) / "snippet.py"
        snippet_path.write_text(_PREAMBLE + "\n" + code)

        env = {"FM_OUT_DIR": out_dir, "PATH": "/usr/bin:/bin"}
        if extra_env:
            env.update(extra_env)

        import os

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

        return ExecResult(
            ok=(rc == 0 and not timed_out),
            stdout=stdout,
            stderr=stderr,
            returncode=rc,
            timed_out=timed_out,
            artifacts=artifacts,
            artifact_files=artifact_files,
        )
