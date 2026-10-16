"""Reliability metrics: what repeated runs say that one run cannot.

A score from a single run is a point estimate with no error bar, and
``paper/manuscript.md`` Methods has carried a standing TODO to replace it with
K>=5 repeats and 95% intervals. This module is the arithmetic for that, plus the
metrics that only exist once repeats are available: does the agent agree with
itself, does it survive a degraded tool, does its stated confidence mean
anything.

Provenance, in full, is ``docs/ecosystem/hal_adoption.md``. In short: the
consistency, robustness and predictability definitions come from *Towards a
Science of AI Agent Reliability* (arXiv:2602.16666), which is CC BY 4.0, except
outcome consistency, where the paper's formula is degenerate for binary outcomes
and we use the ``(2p-1)^2`` form stated on the project's public reliability
dashboard instead. That disagreement is derived and documented in
``hal_adoption.md`` section 3. Nothing here is derived from any HAL source code.

Three conventions hold throughout:

* **Too little data returns ``None``, never ``0.0``.** A zero is a measurement;
  ``None`` is the absence of one. The function this replaces
  (``scripts/demo_dashboard.py::_ci95``) returned ``0.0`` for a single run, which
  is why the site's error bars have never drawn: the renderer's ``ci > 0`` guard
  cannot tell "no variance" from "no data".
* **Pure functions, standard library only.** No numpy, no I/O, no network. The
  default pixi environment has no numpy and CI must keep running there.
* **Higher is better, everywhere.** Every metric is oriented so 1.0 is the good
  end, including the ones the source literature reports as errors.
"""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Mapping, Sequence

__all__ = [
    "auroc",
    "bootstrap_ci",
    "brier",
    "calibration_ece",
    "outcome_consistency",
    "proportion",
    "record_consistency",
    "resource_consistency",
    "robustness_ratio",
    "student_t_ci",
    "trajectory_consistency_dist",
    "trajectory_consistency_seq",
]

# Two-sided t_{0.975} by degrees of freedom, falling back to the normal value.
# Small tables beat a scipy dependency for the 3-7 repeats we actually run.
_T_975 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
}


# ---------------------------------------------------------------------------
# Consistency: does the agent agree with itself?
# ---------------------------------------------------------------------------


def record_consistency(scores: Sequence[float], *, pass_threshold: float = 0.9) -> float | None:
    """Self-agreement of one record across repeats, as ``(2p-1)^2``.

    ``p`` is the fraction of repeats that pass. The result is 1.0 when every
    repeat agrees (always passes, or always fails) and 0.0 at an even split,
    smoothly in between, with no clipping needed.

    Repère's scores are continuous in [0, 1], not binary, so they are binarised
    at ``pass_threshold`` — the same 0.9 default the RCA runner already uses for
    its pass rate. Consistency is about agreement on the *outcome*; variance in
    the score itself is what ``student_t_ci`` reports.

    Returns ``None`` for fewer than two repeats.

    Source: the reliability dashboard's stated formula. The companion paper
    gives a variance ratio instead, which collapses to the constant
    ``1 - K/(K-1)`` for Bernoulli draws; see ``docs/ecosystem/hal_adoption.md``
    section 3 for the derivation and why this form is used.
    """
    if len(scores) < 2:
        return None
    p = sum(1 for s in scores if s >= pass_threshold) / len(scores)
    return (2.0 * p - 1.0) ** 2


def outcome_consistency(
    scores_by_record: Sequence[Sequence[float]], *, pass_threshold: float = 0.9
) -> float | None:
    """Mean of :func:`record_consistency` over every record with enough repeats.

    Records with fewer than two repeats are skipped, not scored zero. Returns
    ``None`` when no record qualifies.
    """
    per_record = [
        c
        for scores in scores_by_record
        if (c := record_consistency(scores, pass_threshold=pass_threshold)) is not None
    ]
    if not per_record:
        return None
    return sum(per_record) / len(per_record)


def resource_consistency(by_resource: Mapping[str, Sequence[float]]) -> float | None:
    """How stable the agent's resource use is across repeats: ``exp(-mean CV)``.

    ``by_resource`` maps a resource name (cost_usd, latency_s, total_tokens,
    n_tool_calls) to its value on each repeat. Per resource the coefficient of
    variation is ``sd/mean``; the score is ``exp(-mean CV)``, so identical usage
    every time scores 1.0 and wild swings decay towards 0.

    A resource that is zero on every repeat has no variation and contributes
    ``CV = 0``. This matters here more than in the source setting: a local model
    costs zero dollars on every run, and that is perfect consistency, not an
    undefined ratio. Negative values raise, since no resource we measure can be
    negative and a negative mean would silently flip the sign of the CV.

    Returns ``None`` if no resource has at least two values.
    """
    cvs: list[float] = []
    for name, values in by_resource.items():
        if len(values) < 2:
            continue
        if any(v < 0 for v in values):
            raise ValueError(f"resource {name!r} has a negative value")
        mean = sum(values) / len(values)
        if mean == 0:
            cvs.append(0.0)  # all zero: no variation
            continue
        cvs.append(statistics.stdev(values) / mean)
    if not cvs:
        return None
    return math.exp(-sum(cvs) / len(cvs))


def _jensen_shannon(p: Mapping[str, float], q: Mapping[str, float]) -> float:
    """Jensen-Shannon divergence in bits, so the result lies in [0, 1]."""
    keys = set(p) | set(q)
    total = 0.0
    for k in keys:
        pk, qk = p.get(k, 0.0), q.get(k, 0.0)
        mk = 0.5 * (pk + qk)
        if pk > 0:
            total += 0.5 * pk * math.log2(pk / mk)
        if qk > 0:
            total += 0.5 * qk * math.log2(qk / mk)
    return min(1.0, max(0.0, total))


def _as_distribution(trace: Sequence[str]) -> dict[str, float]:
    counts: dict[str, float] = {}
    for step in trace:
        counts[step] = counts.get(step, 0.0) + 1.0
    n = sum(counts.values())
    return {k: v / n for k, v in counts.items()}


def trajectory_consistency_dist(traces: Sequence[Sequence[str]]) -> float | None:
    """Agreement in *which* tools were used: ``1 - mean pairwise JSD``.

    Each trace is the sequence of tool names the agent called. Order is ignored
    here — two runs that call the same three tools in a different order are
    treated as identical. :func:`trajectory_consistency_seq` is the ordered
    counterpart; report both, because an agent can be stable in what it reaches
    for and unstable in how it sequences it.

    Empty traces are kept and treated as their own distribution, since "did
    nothing" is a real and repeatable behaviour. Returns ``None`` for fewer than
    two traces.
    """
    if len(traces) < 2:
        return None
    dists = [_as_distribution(t) if t else {"<empty>": 1.0} for t in traces]
    pairs = [
        _jensen_shannon(dists[i], dists[j])
        for i in range(len(dists))
        for j in range(i + 1, len(dists))
    ]
    return 1.0 - sum(pairs) / len(pairs)


def _levenshtein(a: Sequence[str], b: Sequence[str]) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ai in enumerate(a, start=1):
        cur = [i]
        for j, bj in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (0 if ai == bj else 1)))
        prev = cur
    return prev[-1]


def trajectory_consistency_seq(traces: Sequence[Sequence[str]]) -> float | None:
    """Agreement in the *order* of tool calls: ``1 - mean normalised edit distance``.

    Levenshtein distance between tool-name sequences, divided by the longer
    sequence so it lands in [0, 1]. Two empty traces count as identical.
    Returns ``None`` for fewer than two traces.
    """
    if len(traces) < 2:
        return None
    dists: list[float] = []
    for i in range(len(traces)):
        for j in range(i + 1, len(traces)):
            a, b = traces[i], traces[j]
            longest = max(len(a), len(b))
            dists.append(0.0 if longest == 0 else _levenshtein(a, b) / longest)
    return 1.0 - sum(dists) / len(dists)


# ---------------------------------------------------------------------------
# Robustness: does it survive a degraded environment?
# ---------------------------------------------------------------------------


def robustness_ratio(acc_perturbed: float, acc_baseline: float) -> float | None:
    """``min(acc_perturbed / acc_baseline, 1)`` — accuracy retained under stress.

    Used for all three robustness phases (fault injection, structural
    perturbation, prompt paraphrase); the phase is what differs, not the
    arithmetic. Clamped at 1 so that scoring *better* under perturbation reads as
    "fully robust" rather than as a bonus, since beating your own baseline on a
    degraded input means the baseline is noisy, not that the agent is superhuman.

    Returns ``None`` when the baseline is zero: a ratio against zero says nothing
    about robustness, and an agent that fails the clean task has no robustness to
    measure.
    """
    if acc_baseline <= 0:
        return None
    return min(acc_perturbed / acc_baseline, 1.0)


# ---------------------------------------------------------------------------
# Predictability: does its stated confidence mean anything?
# ---------------------------------------------------------------------------


def calibration_ece(
    confidences: Sequence[float], outcomes: Sequence[float], *, bins: int = 10
) -> float | None:
    """``1 - ECE``: how close stated confidence comes to observed accuracy.

    Tasks are binned by confidence; each bin contributes the gap between its mean
    confidence and its mean outcome, weighted by how many tasks it holds. 1.0 is
    perfect calibration.

    Note the failure mode this cannot see: a model that says 0.7 on everything
    and is right 70% of the time is perfectly calibrated and completely
    uninformative. :func:`auroc` is what catches that, so report both.

    Returns ``None`` for empty input.
    """
    if not confidences or len(confidences) != len(outcomes):
        if len(confidences) != len(outcomes):
            raise ValueError("confidences and outcomes must be the same length")
        return None
    buckets: list[list[tuple[float, float]]] = [[] for _ in range(bins)]
    for c, y in zip(confidences, outcomes, strict=True):
        idx = min(bins - 1, int(c * bins))
        buckets[idx].append((c, y))
    n = len(confidences)
    ece = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        mean_conf = sum(c for c, _ in bucket) / len(bucket)
        mean_out = sum(y for _, y in bucket) / len(bucket)
        ece += (len(bucket) / n) * abs(mean_out - mean_conf)
    return 1.0 - ece


def brier(confidences: Sequence[float], outcomes: Sequence[float]) -> float | None:
    """``1 - mean squared error`` between stated confidence and outcome.

    A proper scoring rule: it rewards being both calibrated and decisive, which
    is why it is the single number the source work aggregates predictability on.
    Returns ``None`` for empty input.
    """
    if len(confidences) != len(outcomes):
        raise ValueError("confidences and outcomes must be the same length")
    if not confidences:
        return None
    return 1.0 - sum((c - y) ** 2 for c, y in zip(confidences, outcomes, strict=True)) / len(
        confidences
    )


def auroc(
    confidences: Sequence[float],
    outcomes: Sequence[float],
    *,
    pass_threshold: float = 0.9,
) -> float | None:
    """Probability that a successful task was given higher confidence than a failed one.

    Ties count as half, which is the standard convention and matters here because
    a model that reports the same confidence everywhere would otherwise score 0
    rather than the correct 0.5.

    Returns ``None`` unless both a success and a failure are present: with one
    class the quantity is undefined, and returning 0.5 would look like a
    measurement of an uninformative model rather than the absence of data.
    """
    if len(confidences) != len(outcomes):
        raise ValueError("confidences and outcomes must be the same length")
    succ = [c for c, y in zip(confidences, outcomes, strict=True) if y >= pass_threshold]
    fail = [c for c, y in zip(confidences, outcomes, strict=True) if y < pass_threshold]
    if not succ or not fail:
        return None
    wins = sum(1.0 if s > f else 0.5 if s == f else 0.0 for s in succ for f in fail)
    return wins / (len(succ) * len(fail))


# ---------------------------------------------------------------------------
# Integrity: proportions over per-item booleans the scorers already produce
# ---------------------------------------------------------------------------


def proportion(flags: Sequence[bool]) -> float | None:
    """Fraction of items where a flag holds. ``None`` for empty input.

    The integrity metrics are all proportions over booleans the deterministic
    and typed scorers already emit, so they share one implementation and differ
    only in which flag is counted:

    ============================  =========================================
    ``citation_fabrication_rate`` a ``[S#]`` resolved to no provided source
    ``grounding_rate``            the cited passage supported the claim
    ``overclaim_rate``            the report claimed success on a failed run
    ``abstention_accuracy``       the agent correctly declined to answer
    ``cutoff_compliance``         no retrieval crossed the item's cutoff date
    ============================  =========================================

    Orientation is the caller's responsibility: pass the flag whose *true* means
    the good outcome, so the result reads 1.0-is-better like everything else.
    ``citation_fabrication_rate`` and ``overclaim_rate`` are the exceptions that
    are reported as rates, where lower is better; the leaderboard renders those
    with the opposite colour scale and the glossary says so.
    """
    if not flags:
        return None
    return sum(1 for f in flags if f) / len(flags)


# ---------------------------------------------------------------------------
# Intervals. Two of them, over two different populations.
# ---------------------------------------------------------------------------


def student_t_ci(values: Sequence[float]) -> float | None:
    """Half-width of a 95% interval on the mean **over repeat runs**.

    Student-t, because we run 3-7 repeats and the normal value understates the
    interval badly at that size (t is 2.776 at n=5, against 1.96).

    Returns ``None`` for fewer than two values. The function this replaces
    returned ``0.0``, which a renderer cannot distinguish from a genuinely
    zero-width interval — the reason the site has never drawn an error bar.

    Use this when the population is *runs of the same configuration*. Use
    :func:`bootstrap_ci` when it is *records within a suite*.
    """
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    se = math.sqrt(var / n)
    return _T_975.get(n - 1, 1.96) * se


def bootstrap_ci(
    values: Sequence[float],
    *,
    n_boot: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float] | None:
    """Percentile bootstrap interval on the mean **over records**.

    Moved unchanged from ``repere_suites.rca.run``, which is where it was first
    written. Seeded, so a summary is reproducible from the same inputs.

    Returns ``(lo, hi)``, or ``None`` for fewer than two values.

    Use this when the population is *records within a suite* — the question
    "would another sample of records give a different suite mean". Use
    :func:`student_t_ci` for repeats of one configuration. Comparing one to the
    other compares different things, which is why the glossary states the
    population for each.
    """
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(n_boot))
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return (lo, hi)
