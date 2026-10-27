"""The RCA Atlas pull: hashes are enforced, rows are never committed.

No test here touches the network; the opener is injected.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from repere_suites.atlas import (
    AtlasHashMismatch,
    cache_dir,
    fetch_atlas,
    load_atlas,
    load_pins,
)

REPO = Path(__file__).resolve().parents[1]

ROWS = [{"id": "t-1", "question": "q1"}, {"id": "t-2", "question": "q2"}]
BODY = ("\n".join(json.dumps(r) for r in ROWS) + "\n").encode()


def _pins(body: bytes = BODY, rows: int = 2) -> dict:
    return {
        "repo": "example/atlas",
        "commit": "0" * 40,
        "files": {
            "toy": {
                "path": "src/atlas_eval/datasets/toy_v1.jsonl",
                "sha256": hashlib.sha256(body).hexdigest(),
                "rows": rows,
            }
        },
    }


@pytest.fixture(autouse=True)
def _private_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("REPERE_EVAL_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


def test_fetch_verifies_then_load_reads_rows():
    seen = []

    def opener(req):
        seen.append(req.full_url)
        return BODY

    pins = _pins()
    fetch_atlas(pins=pins, opener=opener)
    assert seen == [
        "https://raw.githubusercontent.com/example/atlas/" + "0" * 40 + "/src/atlas_eval/datasets/toy_v1.jsonl"
    ]
    assert load_atlas("toy", pins=pins) == ROWS


def test_tampered_download_is_refused_and_not_written():
    pins = _pins()
    with pytest.raises(AtlasHashMismatch):
        fetch_atlas(pins=pins, opener=lambda req: BODY + b'{"id": "t-3"}\n')
    assert not (cache_dir(pins) / "toy_v1.jsonl").exists()


def test_edited_cache_is_refused_at_load():
    pins = _pins()
    fetch_atlas(pins=pins, opener=lambda req: BODY)
    (cache_dir(pins) / "toy_v1.jsonl").write_bytes(BODY.replace(b"q1", b"q1 edited"))
    with pytest.raises(AtlasHashMismatch):
        load_atlas("toy", pins=pins)


def test_verified_cache_is_not_downloaded_again():
    pins = _pins()
    fetch_atlas(pins=pins, opener=lambda req: BODY)

    def no_network(req):
        raise AssertionError("downloaded a file that was already verified")

    fetch_atlas(pins=pins, opener=no_network)


def test_missing_cache_names_the_pull_command():
    with pytest.raises(FileNotFoundError, match="scripts/pull_atlas.py"):
        load_atlas("toy", pins=_pins())


def test_row_count_is_checked():
    pins = _pins(rows=3)
    fetch_atlas(pins=pins, opener=lambda req: BODY)
    with pytest.raises(ValueError, match="2 rows"):
        load_atlas("toy", pins=pins)


def test_token_is_sent_only_when_set(monkeypatch):
    headers = []
    pins = _pins()
    fetch_atlas(pins=pins, opener=lambda req: headers.append(req.get_header("Authorization")) or BODY, force=True)
    monkeypatch.setenv("GITHUB_TOKEN", "t0k")
    fetch_atlas(pins=pins, opener=lambda req: headers.append(req.get_header("Authorization")) or BODY, force=True)
    assert headers == [None, "Bearer t0k"]


def test_unknown_name_is_an_error():
    with pytest.raises(KeyError):
        fetch_atlas(["nope"], pins=_pins(), opener=lambda req: BODY)


def test_shipped_pins_are_hashes_only():
    pins = load_pins()
    assert len(pins["commit"]) == 40
    for name, spec in pins["files"].items():
        assert set(spec) <= {"path", "sha256", "rows"}, name
        assert len(spec["sha256"]) == 64, name


def test_no_pinned_atlas_file_is_committed():
    """Atlas rows are proprietary and owned upstream: no tracked file may be one."""
    pinned = {spec["sha256"] for spec in load_pins()["files"].values()}
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True
    ).stdout.split(b"\0")
    hits = []
    for rel in filter(None, tracked):
        p = REPO / rel.decode()
        if p.is_file() and p.suffix in {".jsonl", ".json", ".yaml", ".yml"}:
            if hashlib.sha256(p.read_bytes()).hexdigest() in pinned:
                hits.append(rel.decode())
    assert not hits, f"pinned Atlas datasets committed to Repère: {hits}"
