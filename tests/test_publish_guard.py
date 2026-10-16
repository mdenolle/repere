"""Tests for the outbound publish guard.

The threat model: runs happen on a private GPU host that pushes to git without a
human in the loop. Every test here is a negative control — something that must
be refused — because a guard nobody has watched fail is a guess. The positive
case is one test at the end.

Mirrors the discipline of `tests/test_no_holdout_in_repo.py`, which guards the
same data in the other direction.
"""

from __future__ import annotations

import json

import pytest

from repere.leaderboard import build_leaderboard
from repere.publish import (
    PUBLISHABLE_ROW_FIELDS,
    PublishError,
    check_payload,
    write_board,
)


def _payload(**row_overrides) -> dict:
    row = {
        "rank": 1,
        "model_id": "qwen2.5:7b",
        "agent_condition": "generic-coding-agent",
        "suite": "synthetic_stalta",
        "score_mean": 0.2,
        "score_ci95": None,
        "score_runs": [0.2],
        "n_epochs": 1,
        "cost_usd": 0.0,
        "n_completed": 11,
        "n_total": 11,
        "phase": "baseline",
        "on_frontier_cost": True,
        "on_frontier_tokens": True,
    }
    row.update(row_overrides)
    return {"schema_version": "0.2", "leaderboard": [row]}


# ---------------------------------------------------------------------------
# 1. The allowlist fails closed
# ---------------------------------------------------------------------------


def test_an_unknown_field_is_refused():
    """A denylist would let a new field through. This must fail closed."""
    with pytest.raises(PublishError, match="allowlist"):
        check_payload(_payload(expected_onset_utc="2001-02-28T18:54:32Z"))


def test_the_error_says_how_to_allow_a_legitimate_field():
    with pytest.raises(PublishError, match="PUBLISHABLE_ROW_FIELDS"):
        check_payload(_payload(some_new_metric=0.5))


# ---------------------------------------------------------------------------
# 2. No free text leaves
# ---------------------------------------------------------------------------


def test_a_scorer_explanation_is_refused():
    """The RCA per-sample `explanation` can state the oracle's reference value."""
    with pytest.raises(PublishError, match="free text"):
        check_payload(
            _payload(run_file="ok.json", agent_condition="offset -2.27 s, within 0.5 s tolerance")
        )


def test_a_model_completion_is_refused():
    with pytest.raises(PublishError, match="free text"):
        check_payload(_payload(skill_name="The P arrival is clear at 18:54:32 on UW.LON"))


def test_identifier_shaped_strings_pass():
    check_payload(_payload(model_id="claude-haiku-4-5-20251001"))
    check_payload(_payload(agent_condition="stalta-detection+skill-v0.3"))
    check_payload(_payload(suite="sta_lta.intent_extraction"))


def test_nested_free_text_in_the_reliability_block_is_refused():
    with pytest.raises(PublishError, match="free text"):
        check_payload(_payload(reliability={"note": "grounding failed on the Nisqually passage"}))


def test_a_score_runs_list_must_hold_numbers_only():
    with pytest.raises(PublishError, match="non-numeric"):
        check_payload(_payload(score_runs=["0.2", "explanation"]))


# ---------------------------------------------------------------------------
# 3. Held-out vocabulary never appears
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "needle",
    ["expected_detection", "stalta_params", "expected_tools", "SECRET_SEED"],
)
def test_holdout_field_names_are_refused_anywhere_in_the_payload(needle):
    payload = _payload()
    payload["notes"] = [f"debug: {needle} was 3"]
    with pytest.raises(PublishError, match="held-out"):
        check_payload(payload)


# ---------------------------------------------------------------------------
# 4. Nothing is written when the check fails
# ---------------------------------------------------------------------------


def test_a_refused_payload_does_not_reach_disk(tmp_path):
    """On a host that auto-commits, a file written before validation is published."""
    out = tmp_path / "board.json"
    with pytest.raises(PublishError):
        write_board(_payload(secret_gold="hi"), out)
    assert not out.exists()


# ---------------------------------------------------------------------------
# 5. Advisory warnings, which do not stop a publish
# ---------------------------------------------------------------------------


def test_missing_provenance_warns_but_does_not_block():
    warnings = check_payload(_payload())
    assert any("provenance" in w for w in warnings)


def test_unpinned_weights_and_mixed_hosts_warn():
    payload = _payload(host_id="abc123")
    payload["leaderboard"].append({**payload["leaderboard"][0], "rank": 2, "host_id": "def456"})
    payload["provenance"] = {"warnings": [], "unpinned_models": ["qwen2.5:7b"]}
    warnings = check_payload(payload)
    assert any("unpinned" in w for w in warnings)
    assert any("different hosts" in w for w in warnings)


def test_single_run_rows_warn():
    assert any("single-run" in w for w in check_payload(_payload()))


# ---------------------------------------------------------------------------
# 6. The positive case: a real board passes
# ---------------------------------------------------------------------------


def test_a_real_built_board_passes_the_guard(tmp_path):
    payload = build_leaderboard(
        [
            {
                "model_id": "qwen2.5:7b",
                "suite": "codameter",
                "score_runs": [1.0, 1.0, 0.98, 1.0, 0.99],
                "cost_usd": 0.0,
                "in_tokens": 4000,
                "out_tokens": 900,
                "n_completed": 20,
                "n_total": 20,
                "openness": "open-source-open-weight",
            }
        ]
    )
    # build_leaderboard emits exactly the allowlisted fields, which is the
    # contract this pins: the two lists cannot drift apart silently.
    extra = set(payload["leaderboard"][0]) - PUBLISHABLE_ROW_FIELDS
    assert not extra, f"build_leaderboard emits unpublishable fields: {sorted(extra)}"

    out = tmp_path / "board.json"
    warnings = write_board(payload, out)
    assert out.exists()
    assert json.loads(out.read_text())["schema_version"] == "0.2"
    assert not any("single-run" in w for w in warnings)


def test_the_committed_board_passes_the_guard():
    """The board in the repository must itself be publishable."""
    from pathlib import Path

    board = Path(__file__).resolve().parents[1] / "site" / "data" / "leaderboard.json"
    check_payload(json.loads(board.read_text()))
