"""Guard against Pixi lock drift for the editable local package metadata."""

from __future__ import annotations

import re
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
PIXI_LOCK = ROOT / "pixi.lock"


def _frugalmind_lock_block() -> str:
    text = PIXI_LOCK.read_text(encoding="utf-8")
    match = re.search(
        r"^- pypi: \./\n  name: frugalmind\n(?P<body>.*?)(?=^- |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, "pixi.lock must contain the editable frugalmind package entry"
    return match.group("body")


def _lock_requires_dist(body: str) -> list[str]:
    requires: list[str] = []
    capture = False
    for line in body.splitlines():
        if line == "  requires_dist:":
            capture = True
            continue
        if capture:
            if not line.startswith("  - "):
                break
            requires.append(line.removeprefix("  - "))
    return requires


def _requirement_name(requirement: str) -> str:
    match = re.match(r"[A-Za-z0-9_.-]+", requirement)
    assert match is not None, f"unsupported requirement format: {requirement}"
    return match.group(0).replace("_", "-").lower()


def test_pixi_lock_matches_pyproject_metadata():
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = pyproject["project"]
    lock_body = _frugalmind_lock_block()
    requires_dist = _lock_requires_dist(lock_body)

    # Lock format v6 recorded the editable package's version; v7 (pixi >= 0.7x)
    # does not carry it for path dependencies, so only check when present.
    if "  version: " in lock_body:
        assert f"  version: {project['version']}" in lock_body

    for dependency in project["dependencies"]:
        name = _requirement_name(dependency)
        assert any(_requirement_name(req) == name for req in requires_dist)

    for extra, dependencies in project["optional-dependencies"].items():
        for dependency in dependencies:
            name = _requirement_name(dependency)
            assert any(
                _requirement_name(req) == name and f"extra == '{extra}'" in req
                for req in requires_dist
            )
