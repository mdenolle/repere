"""Tests for `repere.pareto`.

Worked by hand, not by rerunning the implementation. The cases that matter:

  1. A point beaten only by a *mixture* of two others is off the frontier. This
     is the whole reason the frontier is a convex hull rather than a staircase,
     and it is the one behaviour a naive dominance sweep gets wrong.
  2. The origin is a member, so a cheap bad agent does not get the frontier for
     free.
  3. Paying more for less is never on the frontier, even though the geometric
     hull turns back down.
  4. Every local model costs $0, so the all-zero-cost column has to behave.
"""

from __future__ import annotations

import pytest

from repere.pareto import compute_frontier, frontier_points, mark_frontier


def _rows(*pairs: tuple[str, float, float]) -> list[dict]:
    return [{"model_id": m, "cost_usd": c, "score_mean": s} for m, c, s in pairs]


def _on(rows: list[dict]) -> set[str]:
    idx = compute_frontier(rows, x_field="cost_usd", y_field="score_mean")
    return {rows[i]["model_id"] for i in idx}


# ---------------------------------------------------------------------------
# 1. The hull, and why it is not a staircase
# ---------------------------------------------------------------------------


def test_a_point_beaten_only_by_a_mixture_is_off_the_frontier():
    """$2/0.60 survives a staircase sweep and must not survive the hull.

    A at $1 scores 0.50; C at $3 scores 0.90. Deploying A half the time and C
    the other half costs $2 for an expected 0.70, which beats B's 0.60 at the
    same price. No single agent dominates B, so a staircase keeps it.
    """
    rows = _rows(("A", 1.0, 0.50), ("B", 2.0, 0.60), ("C", 3.0, 0.90))
    assert _on(rows) == {"A", "C"}


def test_a_point_above_the_mixture_line_stays():
    """Same three costs; B now scores 0.80, above the 0.70 the mixture offers."""
    rows = _rows(("A", 1.0, 0.50), ("B", 2.0, 0.80), ("C", 3.0, 0.90))
    assert _on(rows) == {"A", "B", "C"}


def test_a_point_exactly_on_the_mixture_line_is_not_a_vertex():
    """B at exactly 0.70 is achievable by mixing, so it adds nothing."""
    rows = _rows(("A", 1.0, 0.50), ("B", 2.0, 0.70), ("C", 3.0, 0.90))
    assert _on(rows) == {"A", "C"}


# ---------------------------------------------------------------------------
# 2. The origin
# ---------------------------------------------------------------------------


def test_the_origin_keeps_a_cheap_bad_agent_off_the_frontier():
    """Without the origin, the cheapest agent is on the frontier by default.

    D costs $0.10 and scores 0.02 — worse than not deploying anything, per
    dollar. E at $1.00 / 0.90 makes D's price-performance indefensible.
    """
    rows = _rows(("D", 0.10, 0.02), ("E", 1.00, 0.90))
    assert _on(rows) == {"E"}
    # Drop the origin and D comes back, which is the behaviour being prevented.
    idx = compute_frontier(rows, x_field="cost_usd", y_field="score_mean", include_origin=False)
    assert {rows[i]["model_id"] for i in idx} == {"D", "E"}


def test_the_origin_itself_is_never_returned_as_a_row():
    rows = _rows(("A", 1.0, 0.5))
    assert _on(rows) == {"A"}


# ---------------------------------------------------------------------------
# 3. Truncation at the best score
# ---------------------------------------------------------------------------


def test_paying_more_for_less_is_off_the_frontier():
    rows = _rows(("cheap", 1.0, 0.90), ("pricey", 5.0, 0.40))
    assert _on(rows) == {"cheap"}


def test_the_most_expensive_model_is_not_automatically_on_the_frontier():
    """HAL's finding 1, in miniature: the costliest model usually is not."""
    rows = _rows(("small", 0.5, 0.80), ("mid", 1.0, 0.85), ("huge", 9.0, 0.82))
    assert "huge" not in _on(rows)


# ---------------------------------------------------------------------------
# 4. Zero-cost local models
# ---------------------------------------------------------------------------


def test_free_models_only_the_best_takes_the_frontier():
    """Every Ollama row bills $0, so the x axis collapses to a single column."""
    rows = _rows(("olmo", 0.0, 0.37), ("qwen", 0.0, 1.00), ("llama", 0.0, 0.41))
    assert _on(rows) == {"qwen"}


def test_a_free_model_and_a_paid_model_can_share_the_frontier():
    rows = _rows(("qwen", 0.0, 0.75), ("haiku", 0.03, 1.00))
    assert _on(rows) == {"qwen", "haiku"}


def test_a_free_perfect_model_takes_the_whole_frontier():
    """The July board's actual result on dv/v: free and perfect ends the argument."""
    rows = _rows(("qwen", 0.0, 1.00), ("haiku", 0.0349, 1.00))
    assert _on(rows) == {"qwen"}


# ---------------------------------------------------------------------------
# 5. Ties, degenerate inputs, bad data
# ---------------------------------------------------------------------------


def test_tied_rows_are_all_flagged():
    rows = _rows(("a", 1.0, 0.9), ("b", 1.0, 0.9))
    assert _on(rows) == {"a", "b"}


def test_single_row_and_empty_input():
    assert _on(_rows(("only", 2.0, 0.3))) == {"only"}
    assert compute_frontier([], x_field="cost_usd", y_field="score_mean") == set()


def test_rows_missing_a_field_are_skipped_not_treated_as_free():
    rows = _rows(("measured", 1.0, 0.9))
    rows.append({"model_id": "unmeasured", "score_mean": 0.95})
    assert _on(rows) == {"measured"}


def test_non_numeric_and_boolean_values_are_skipped():
    rows = _rows(("good", 1.0, 0.9))
    rows.append({"model_id": "bad", "cost_usd": "free", "score_mean": 1.0})
    rows.append({"model_id": "worse", "cost_usd": True, "score_mean": 1.0})
    assert _on(rows) == {"good"}


def test_negative_cost_raises():
    with pytest.raises(ValueError, match="negative cost"):
        frontier_points([(-1.0, 0.5)])


# ---------------------------------------------------------------------------
# 6. Vertices, and the two-axis API
# ---------------------------------------------------------------------------


def test_frontier_points_returns_vertices_cheapest_first():
    pts = frontier_points([(3.0, 0.9), (1.0, 0.5), (2.0, 0.6)])
    assert pts[0] == (0.0, 0.0)
    assert pts[-1] == (3.0, 0.9)
    assert (2.0, 0.6) not in pts
    assert [p[0] for p in pts] == sorted(p[0] for p in pts)


def test_mark_frontier_writes_a_flag_on_every_row():
    rows = _rows(("A", 1.0, 0.50), ("B", 2.0, 0.60), ("C", 3.0, 0.90))
    for r in rows:
        r["total_tokens"] = {"A": 900, "B": 500, "C": 4000}[r["model_id"]]

    mark_frontier(rows, x_field="cost_usd", y_field="score_mean", flag_field="on_frontier_cost")
    mark_frontier(
        rows,
        x_field="total_tokens",
        y_field="score_mean",
        flag_field="on_frontier_tokens",
    )

    assert all("on_frontier_cost" in r and "on_frontier_tokens" in r for r in rows)
    by_id = {r["model_id"]: r for r in rows}
    # The two axes disagree: B is off the dollar frontier but on the token one,
    # because it is the cheapest in tokens. This is why both are reported.
    assert by_id["B"]["on_frontier_cost"] is False
    assert by_id["B"]["on_frontier_tokens"] is True
