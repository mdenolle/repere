"""What has to travel with a number produced on a machine nobody else can reach.

Repère's runs are moving to a private GPU host behind a VPN, while the board
stays public. That splits every quantity on the board into two kinds, and the
split is the whole point of this module:

**Invariant.** Should be identical on any machine, given the same pinned inputs.
The deterministic scores, the token counts, the dataset hashes, the frontier. If
one of these changes when the host changes, something is wrong and we want to
know.

**Host-bound.** Cannot be compared across machines at all. Wall-clock latency,
energy, throughput, and anything derived from them. A 7B model is not "slower
than" a cloud model because one ran on four GPUs and the other over an API; that
comparison is a property of the hosts, not the models. These fields carry a
``host_id`` and the site must refuse to plot them across hosts.

The pin that makes invariance real is the **model digest, not the tag.**
``qwen2.5:7b`` is a moving pointer: Ollama can serve a different quantization on
two machines under the same name, and the leaderboard would show the difference
as a model difference. ``repere_suites.rca.cost`` already flags API models whose
id is not pinned, but exempts local providers from that check
(``local_providers``), which is exactly the case a private GPU host makes
dangerous. :func:`capture_ollama_models` closes it by recording the digest and
quantization level Ollama reports for every model actually served.

Nothing here raises when a fact cannot be collected. A missing GPU query or an
Ollama server that is not running records ``None``, because a provenance block
that fails the run is a provenance block people switch off.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "HOST_BOUND_FIELDS",
    "HostProfile",
    "ModelPin",
    "RunProvenance",
    "capture_host",
    "capture_ollama_models",
    "capture_run_provenance",
    "dataset_hashes",
]

# Board fields whose value is a property of the machine, not of the system under
# test. Two rows with different `host_id` may be compared on anything else and
# on none of these.
HOST_BOUND_FIELDS = frozenset(
    {
        "latency_s_mean",
        "latency_s_ci95",
        "energy_kwh",
        "gco2e",
        # Resource consistency averages the coefficient of variation over cost,
        # latency and tokens. Latency is in there, so the whole metric inherits
        # the host binding even though two of its three inputs do not.
        "consistency_resource",
    }
)

_DEFAULT_OLLAMA = "http://localhost:11434"


def _run(cmd: list[str], *, timeout: float = 10.0) -> str | None:
    """Run a command, returning stripped stdout or ``None`` on any failure."""
    if shutil.which(cmd[0]) is None:
        return None
    try:
        out = subprocess.run(  # noqa: S603 - fixed argv, no shell
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


@dataclass(frozen=True)
class HostProfile:
    """The machine. Every field here is host-bound by definition."""

    host_id: str
    platform: str
    python_version: str
    cpu_count: int | None = None
    gpu_count: int | None = None
    gpu_models: list[str] = field(default_factory=list)
    ollama_version: str | None = None
    label: str | None = None

    @property
    def gpu_summary(self) -> str:
        if not self.gpu_models:
            return "no GPU detected"
        unique = sorted(set(self.gpu_models))
        return f"{self.gpu_count or len(self.gpu_models)}x {', '.join(unique)}"


@dataclass(frozen=True)
class ModelPin:
    """One model as it was actually served, not as it was requested.

    ``digest`` is what makes a local run reproducible somewhere else. Without
    it, two hosts serving different quantizations of ``qwen2.5:7b`` produce
    different scores under the same row label, and the board reads that as a
    finding.
    """

    model_id: str
    provider: str
    digest: str | None = None
    quantization: str | None = None
    parameter_size: str | None = None

    @property
    def pinned(self) -> bool:
        """A local model is pinned only when we know the weights it served."""
        if self.provider in {"ollama", "vllm", "local"}:
            return self.digest is not None
        return True


@dataclass(frozen=True)
class RunProvenance:
    """Everything a public reader needs to attribute a number they cannot rerun."""

    harness_commit: str | None
    harness_dirty: bool | None
    harness_version: str | None
    host: HostProfile
    models: list[ModelPin] = field(default_factory=list)
    sandbox_image: str | None = None
    price_map_version: str | None = None
    dataset_sha256: dict[str, str] = field(default_factory=dict)
    seed: int | None = None
    temperature: float | None = None
    n_epochs: int | None = None
    eval_data_dir_present: bool = False

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["host_bound_fields"] = sorted(HOST_BOUND_FIELDS)
        payload["unpinned_models"] = [m.model_id for m in self.models if not m.pinned]
        return payload

    def warnings(self) -> list[str]:
        """Reasons a reader should not treat this run as fully attributable."""
        out: list[str] = []
        if self.harness_commit is None:
            out.append("harness commit unknown: results are not tied to a code version")
        if self.harness_dirty:
            out.append("harness tree was dirty: the commit does not describe what ran")
        unpinned = [m.model_id for m in self.models if not m.pinned]
        if unpinned:
            out.append(
                "model weights not pinned by digest, so another host may serve "
                f"different weights under the same name: {', '.join(sorted(unpinned))}"
            )
        if not self.dataset_sha256:
            out.append("no dataset hashes recorded: the inputs cannot be verified")
        return out


def capture_host(*, label: str | None = None) -> HostProfile:
    """Describe the machine, as far as it will say.

    ``host_id`` is a short digest of the node name, platform and GPU inventory.
    It is an identity, not a secret: it exists so two rows can be told apart, and
    the hostname itself is not published.
    """
    node = platform.node()
    plat = platform.platform()
    gpu_models: list[str] = []
    raw = _run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
    if raw:
        gpu_models = [line.strip() for line in raw.splitlines() if line.strip()]

    fingerprint = "|".join([node, plat, ",".join(sorted(gpu_models))])
    host_id = hashlib.sha256(fingerprint.encode()).hexdigest()[:12]

    return HostProfile(
        host_id=host_id,
        platform=plat,
        python_version=platform.python_version(),
        cpu_count=os.cpu_count(),
        gpu_count=len(gpu_models) or None,
        gpu_models=gpu_models,
        ollama_version=_ollama_version(),
        label=label or os.environ.get("REPERE_HOST_LABEL"),
    )


def _ollama_base() -> str:
    return os.environ.get("OLLAMA_HOST", _DEFAULT_OLLAMA).rstrip("/")


def _ollama_get(path: str, *, timeout: float = 5.0) -> Any | None:
    url = f"{_ollama_base()}{path}"
    if not url.startswith(("http://", "https://")):
        return None
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None


def _ollama_version() -> str | None:
    data = _ollama_get("/api/version")
    return data.get("version") if isinstance(data, dict) else None


def capture_ollama_models(model_ids: list[str] | None = None) -> list[ModelPin]:
    """Pin every locally served model by the digest Ollama reports.

    This is the check ``rca.cost`` skips for local providers. A tag is a moving
    pointer; the digest is the weights. Returns an empty list when no Ollama
    server answers, and a pin with ``digest=None`` for a requested model the
    server does not have — which is itself worth recording, because it means the
    run used something we could not identify.
    """
    data = _ollama_get("/api/tags")
    available: dict[str, dict[str, Any]] = {}
    if isinstance(data, dict):
        for entry in data.get("models", []) or []:
            name = entry.get("name") or entry.get("model")
            if name:
                available[str(name)] = entry

    wanted = model_ids if model_ids is not None else sorted(available)
    pins: list[ModelPin] = []
    for model_id in wanted:
        entry = available.get(model_id) or available.get(f"{model_id}:latest") or {}
        details = entry.get("details") or {}
        digest = entry.get("digest")
        pins.append(
            ModelPin(
                model_id=model_id,
                provider="ollama",
                digest=str(digest)[:19] if digest else None,
                quantization=details.get("quantization_level"),
                parameter_size=details.get("parameter_size"),
            )
        )
    return pins


def dataset_hashes(datasets_dir: Path) -> dict[str, str]:
    """Collect the sha256 of every exported dataset file from its manifest.

    The export step already writes these (``repere.export.export_suites``), so
    the run does not rehash anything; it copies what the frozen artifact claims,
    which is what a reader would check against.
    """
    out: dict[str, str] = {}
    if not datasets_dir.exists():
        return out
    for manifest in sorted(datasets_dir.rglob("manifest.json")):
        try:
            payload = json.loads(manifest.read_text())
        except (OSError, ValueError):
            continue
        for entry in payload.get("files", []) or []:
            path, sha = entry.get("path"), entry.get("sha256")
            if path and sha:
                out[str(path)] = str(sha)
    return out


def capture_run_provenance(
    *,
    repo_root: Path | None = None,
    model_ids: list[str] | None = None,
    host_label: str | None = None,
    price_map_version: str | None = None,
    seed: int | None = None,
    temperature: float | None = None,
    n_epochs: int | None = None,
) -> RunProvenance:
    """Collect everything attributable about this run, failing at nothing."""
    root = repo_root or Path(__file__).resolve().parents[2]

    commit = _run(["git", "-C", str(root), "rev-parse", "HEAD"])
    status = _run(["git", "-C", str(root), "status", "--porcelain"])
    dirty = None if status is None else bool(status.strip())

    try:
        from importlib.metadata import version as _pkg_version

        harness_version = _pkg_version("repere")
    except Exception:  # pragma: no cover - only when not installed
        harness_version = None

    eval_dir = os.environ.get("REPERE_EVAL_DATA_DIR") or str(root / "data" / "private")

    return RunProvenance(
        harness_commit=commit,
        harness_dirty=dirty,
        harness_version=harness_version,
        host=capture_host(label=host_label),
        models=capture_ollama_models(model_ids),
        sandbox_image=os.environ.get("REPERE_SANDBOX_IMAGE"),
        price_map_version=price_map_version,
        dataset_sha256=dataset_hashes(root / "datasets"),
        seed=seed,
        temperature=temperature,
        n_epochs=n_epochs,
        eval_data_dir_present=Path(eval_dir).is_dir(),
    )
