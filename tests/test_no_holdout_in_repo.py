"""Guard: no held-out row may be committed, or shipped in the wheel.

This is the regression test for a real leak. Nine rows marked
`split: test, visibility: private` were committed in the two real-event
suites, carrying their own answers -- `expected_detection` and the reference
`stalta_params` for STA/LTA, `expected_tools` / `required_cli_args` /
`expected_files` for the GAIA downloader -- and they went out in the `repere`
0.5.1 wheel on PyPI before anyone noticed. `.gitignore` did not catch it
because these files live inside the installed package, not under `data/`.

A benchmark whose answers ship in its own package measures memorisation. Held
out means held out of the repo and out of the distribution, in
REPERE_EVAL_DATA_DIR, merged at load time by each suite's loader.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

SUITES_DIR = Path(__file__).resolve().parents[1] / "src" / "repere_suites"

# (path relative to src/repere_suites, the key holding the row list)
TRUTH_SETS = [
    ("sta_lta/events.yaml", "events"),
    ("synthetic_stalta/cases.yaml", "cases"),
    ("lit_rag/tasks.yaml", "tasks"),
    ("orchestration/tasks.yaml", "tasks"),
    ("pipeline_regression/pipelines.yaml", "pipelines"),
    ("paper_workflow/papers.yaml", "papers"),
    ("gaia_data_downloader/tasks.yaml", "tasks"),
]


def _rows(rel: str, key: str) -> list[dict]:
    path = SUITES_DIR / rel
    if not path.is_file():
        pytest.skip(f"{rel} absent")
    data = yaml.safe_load(path.read_text()) or {}
    rows = data.get(key) or []
    return [r for r in rows if isinstance(r, dict)]


@pytest.mark.parametrize("rel,key", TRUTH_SETS)
def test_no_test_split_row_is_committed(rel, key):
    leaked = [r.get("id") for r in _rows(rel, key) if r.get("split") == "test"]
    assert not leaked, (
        f"{rel} commits {len(leaked)} row(s) with split: test -> {leaked}. "
        "These carry the gold a ranked score is computed from. Move them to "
        "$REPERE_EVAL_DATA_DIR and let the suite's loader merge them."
    )


@pytest.mark.parametrize("rel,key", TRUTH_SETS)
def test_no_private_visibility_row_is_committed(rel, key):
    leaked = [r.get("id") for r in _rows(rel, key) if r.get("visibility") == "private"]
    assert not leaked, (
        f"{rel} commits {len(leaked)} row(s) with visibility: private -> {leaked}. "
        "`private` means the row does not live in this repository."
    )


def test_package_data_patterns_ship_no_holdout_file():
    """Nothing matching a held-out naming convention may be inside the package."""
    offenders = sorted(
        str(p.relative_to(SUITES_DIR))
        for p in SUITES_DIR.rglob("*")
        if p.is_file() and ("_test.yaml" in p.name or p.name.endswith(".test.json"))
    )
    assert not offenders, (
        f"held-out files inside the installed package: {offenders}. "
        "The wheel ships everything package-data matches, so these would be "
        "published to PyPI."
    )


RCA_SEEDS = SUITES_DIR / "rca" / "seeds"

# Held-out seeds committed before this guard existed, awaiting removal from
# the repository (and migration to RCA Atlas, which owns golden items). The
# entry is an assistant template with no stored answer; its test status is
# spent either way, because it has been public. Empty this set when the file
# goes; `test_pending_removals_still_exist` fails until you do.
PENDING_REMOVAL = {"rca-coding-timing-resyncs-hys14-002.yaml"}


def test_no_rca_seed_is_held_out():
    """RCA records ship in the wheel (`seeds/*/*.yaml` in package-data).

    Held-out RCA records belong in $REPERE_RCA_PRIVATE_DIR/records/<family>/,
    which `repere_suites.rca.record_paths` merges at load time. This guard was
    missing until 2026-10-15: the truth-set list above never covered RCA, and
    one template seed carried `split: test`.
    """
    leaked = []
    for p in sorted(RCA_SEEDS.glob("*/*.y*ml")):
        holdout = (yaml.safe_load(p.read_text()) or {}).get("holdout") or {}
        if p.name in PENDING_REMOVAL:
            continue
        if holdout.get("split") == "test" or holdout.get("visibility") == "private":
            leaked.append(p.name)
    assert not leaked, (
        f"RCA seeds marked held out: {leaked}. Move them to "
        "$REPERE_RCA_PRIVATE_DIR/records/<family>/; anything under seeds/ is "
        "committed and published to PyPI."
    )


def test_pending_removals_still_exist():
    """The exception list may only name files that are still there."""
    gone = sorted(n for n in PENDING_REMOVAL if not list(RCA_SEEDS.glob(f"*/{n}")))
    assert not gone, f"remove {gone} from PENDING_REMOVAL; the files are gone"
