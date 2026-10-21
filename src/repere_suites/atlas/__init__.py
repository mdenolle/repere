"""RCA Atlas golden data sets, pulled from their origin repository.

RCA Atlas (``coszo-hub/RCA-Atlas``) owns these items; Repère evaluates models on
them. Nothing here contains a row. ``pins.yaml`` names a commit and the
SHA-256 of each dataset file, ``fetch_atlas()`` downloads the files at that
commit into ``$REPERE_EVAL_DATA_DIR/atlas/<commit>/`` (gitignored, outside the
wheel), and ``load_atlas()`` reads them back after checking the hash again.

Two reasons for pulling instead of copying. One source of truth: a case fixed
in Atlas is fixed for Repère by moving the pin, not by editing a second copy.
And the Atlas licence is proprietary, so Repère may not redistribute a row.

Usage::

    pixi run python scripts/pull_atlas.py          # download and verify
    from repere_suites.atlas import load_atlas
    rows = load_atlas("agent_tasks")

The repository is public today. If it becomes private, set ``GITHUB_TOKEN``
to a token with read access and the fetch sends it.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
PINS_PATH = HERE / "pins.yaml"
_REPO_ROOT = HERE.parents[2]

RAW_URL = "https://raw.githubusercontent.com/{repo}/{commit}/{path}"

Opener = Callable[[urllib.request.Request], bytes]


class AtlasHashMismatch(ValueError):
    """A downloaded or cached file does not match its pinned SHA-256."""


def load_pins(path: Path = PINS_PATH) -> dict[str, Any]:
    pins = yaml.safe_load(path.read_text(encoding="utf-8"))
    for key in ("repo", "commit", "files"):
        if key not in pins:
            raise ValueError(f"{path} has no {key!r}")
    return pins


def cache_dir(pins: dict[str, Any] | None = None) -> Path:
    """Where the pinned files live locally. Resolved per call, so tests can
    point ``REPERE_EVAL_DATA_DIR`` at a temporary directory."""
    pins = pins or load_pins()
    root = Path(os.environ.get("REPERE_EVAL_DATA_DIR", _REPO_ROOT / "data" / "private"))
    return root / "atlas" / pins["commit"]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _default_opener(req: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (fixed https host)
        return resp.read()


def fetch_atlas(
    names: list[str] | None = None,
    *,
    pins: dict[str, Any] | None = None,
    opener: Opener = _default_opener,
    force: bool = False,
) -> dict[str, Path]:
    """Download the pinned files and verify each one before writing it.

    A file already in the cache with the right hash is not downloaded again.
    A hash mismatch raises ``AtlasHashMismatch`` and writes nothing for that
    file, so a moved branch or an edited case can never be scored silently.
    """
    pins = pins or load_pins()
    files = pins["files"]
    names = names or list(files)
    unknown = sorted(set(names) - set(files))
    if unknown:
        raise KeyError(f"not in pins.yaml: {unknown}; known: {sorted(files)}")

    out = cache_dir(pins)
    out.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("GITHUB_TOKEN")
    written: dict[str, Path] = {}
    for name in names:
        spec = files[name]
        target = out / Path(spec["path"]).name
        if not force and target.is_file() and _sha256(target.read_bytes()) == spec["sha256"]:
            written[name] = target
            continue
        url = RAW_URL.format(repo=pins["repo"], commit=pins["commit"], path=spec["path"])
        req = urllib.request.Request(url)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        data = opener(req)
        got = _sha256(data)
        if got != spec["sha256"]:
            raise AtlasHashMismatch(
                f"{name}: {spec['path']} at {pins['commit'][:7]} hashes to {got}, "
                f"pins.yaml expects {spec['sha256']}"
            )
        target.write_bytes(data)
        written[name] = target
    return written


def load_atlas(name: str, *, pins: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Rows of one pinned Atlas dataset, re-verified against its hash."""
    pins = pins or load_pins()
    if name not in pins["files"]:
        raise KeyError(f"not in pins.yaml: {name!r}; known: {sorted(pins['files'])}")
    spec = pins["files"][name]
    path = cache_dir(pins) / Path(spec["path"]).name
    if not path.is_file():
        raise FileNotFoundError(
            f"Atlas dataset {name!r} is not in {path.parent}. "
            "Pull it with: pixi run python scripts/pull_atlas.py"
        )
    data = path.read_bytes()
    if _sha256(data) != spec["sha256"]:
        raise AtlasHashMismatch(f"{path} no longer matches its pin; pull again with --force")
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    if "rows" in spec and len(rows) != spec["rows"]:
        raise ValueError(f"{name}: {len(rows)} rows, pins.yaml says {spec['rows']}")
    return rows


__all__ = [
    "AtlasHashMismatch",
    "PINS_PATH",
    "cache_dir",
    "fetch_atlas",
    "load_atlas",
    "load_pins",
]
