"""The cost-versus-quality frontier.

Repère's whole claim is a comparison on two axes at once: the interesting winner
is the cheapest system that still clears the quality floor. That comparison needs
a frontier, and the repository has not had one since the Chart.js panel was
removed from ``site/app.js`` — ``computeParetoFront`` is still referenced by
``DESIGN.md``, ``CHANGELOG.md`` and the RCA design, and has not existed in the
code for some time. This module is the replacement, in Python rather than
JavaScript so the public board and the RCA harness share one implementation and
one set of tests.

**Convex hull, not a staircase, and the origin is a member.** Both points are
taken from the HAL paper (arXiv:2510.11977), reimplemented from its prose; see
``docs/ecosystem/hal_adoption.md``. The reasoning:

* A *staircase* frontier keeps every point no cheaper option beats. But if agent
  A costs $1 at score 0.5 and agent C costs $3 at score 0.9, you can deploy A on
  half your tasks and C on the other half for $2 at an expected 0.7. Any agent
  sitting at $2 and 0.6 is beaten by that mixture even though no single agent
  beats it. The admissible set is therefore the convex hull, and a point strictly
  inside it is dominated by a strategy you can actually run.
* The *origin* belongs on the hull because not deploying an agent is always
  available, costs nothing and scores nothing. Without it, the cheapest agent is
  trivially on the frontier no matter how badly it scores.

The frontier is truncated at the highest-scoring point. Beyond that, the hull
turns back down: paying more for less is on the geometric hull but is never a
defensible deployment, and a leaderboard that flagged it would be marking a row
as good because it is expensive.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

__all__ = ["compute_frontier", "frontier_points", "mark_frontier"]

_EPS = 1e-12


def _cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def frontier_points(
    points: Sequence[tuple[float, float]], *, include_origin: bool = True
) -> list[tuple[float, float]]:
    """Hull vertices of the cost/quality frontier, cheapest first.

    ``points`` are ``(x, y)`` with **x a cost (lower is better)** and **y a score
    (higher is better)**. Negative costs raise: nothing we measure can be
    negative, and a negative would put the hull on the wrong side of the origin
    without any error.

    Returns the vertices in increasing x, starting at the origin when
    ``include_origin`` and ending at the highest-scoring point.
    """
    for x, _y in points:
        if x < 0:
            raise ValueError(f"negative cost on the x axis: {x}")
    pts = list(points)
    if include_origin:
        pts.append((0.0, 0.0))
    if not pts:
        return []

    # Sort cheapest first; at equal cost the better score leads, so the hull
    # walk sees the useful point before the one it dominates.
    pts = sorted(set(pts), key=lambda p: (p[0], -p[1]))

    # Upper hull by monotone chain: pop while the last turn is not a right turn,
    # which drops any point sitting below the line between its neighbours.
    hull: list[tuple[float, float]] = []
    for p in pts:
        while len(hull) >= 2 and _cross(hull[-2], hull[-1], p) >= -_EPS:
            hull.pop()
        hull.append(p)

    # Truncate at the best score. Everything after it costs more and scores less.
    best_y = max(p[1] for p in hull)
    cut = next(i for i, p in enumerate(hull) if p[1] >= best_y - _EPS)
    return hull[: cut + 1]


def compute_frontier(
    rows: Sequence[dict[str, Any]],
    *,
    x_field: str,
    y_field: str,
    include_origin: bool = True,
) -> set[int]:
    """Indices of the rows sitting on the frontier.

    Rows missing either field, or carrying a non-numeric value, are skipped
    rather than treated as zero — a row with no recorded cost is unmeasured, not
    free, and putting it at the origin would let it claim the frontier.

    Every row whose point coincides with a hull vertex is marked, so tied
    configurations are all flagged rather than one being picked arbitrarily.
    """
    usable: list[tuple[int, tuple[float, float]]] = []
    for i, row in enumerate(rows):
        x, y = row.get(x_field), row.get(y_field)
        if isinstance(x, bool) or isinstance(y, bool):
            continue
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue
        usable.append((i, (float(x), float(y))))
    if not usable:
        return set()

    vertices = set(frontier_points([p for _, p in usable], include_origin=include_origin))
    return {
        i
        for i, p in usable
        if any(abs(p[0] - v[0]) <= _EPS and abs(p[1] - v[1]) <= _EPS for v in vertices)
    }


def mark_frontier(
    rows: Sequence[dict[str, Any]],
    *,
    x_field: str,
    y_field: str,
    flag_field: str,
    include_origin: bool = True,
) -> None:
    """Set ``flag_field`` to True/False on every row, in place.

    Called once per axis. The board reports a dollar frontier and a token
    frontier side by side because they disagree: prices move under a published
    benchmark, and a reader who wants to re-price our numbers under a different
    list needs the token axis to do it.
    """
    on = compute_frontier(rows, x_field=x_field, y_field=y_field, include_origin=include_origin)
    for i, row in enumerate(rows):
        row[flag_field] = i in on
