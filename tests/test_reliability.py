"""Tests for `repere.reliability`.

The contract this file exists to pin, in priority order:

  1. **Too little data returns `None`, never `0.0`.** Every aggregate. This is
     the bug being fixed: `scripts/demo_dashboard.py::_ci95` returned `0.0` for a
     single run, and `site/app.js` guards its error bars on `ci > 0`, so a
     single-run board silently renders as though it had zero variance.
  2. Known-value cases at the ends and the middle of every scale, computed by
     hand rather than by rerunning the implementation.
  3. The orientation convention: 1.0 is the good end of every metric.
"""

from __future__ import annotations

import math

import pytest

from repere.reliability import (
    auroc,
    bootstrap_ci,
    brier,
    calibration_ece,
    outcome_consistency,
    proportion,
    record_consistency,
    resource_consistency,
    robustness_ratio,
    student_t_ci,
    trajectory_consistency_dist,
    trajectory_consistency_seq,
)

# ---------------------------------------------------------------------------
# 1. Insufficient data is None everywhere
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fn", "args"),
    [
        (record_consistency, ([1.0],)),
        (record_consistency, ([],)),
        (outcome_consistency, ([[1.0], [0.0]],)),
        (outcome_consistency, ([],)),
        (resource_consistency, ({"cost_usd": [0.1]},)),
        (resource_consistency, ({},)),
        (trajectory_consistency_dist, ([["a"]],)),
        (trajectory_consistency_seq, ([["a"]],)),
        (calibration_ece, ([], [])),
        (brier, ([], [])),
        (student_t_ci, ([0.5],)),
        (bootstrap_ci, ([0.5],)),
        (proportion, ([],)),
    ],
)
def test_insufficient_data_returns_none(fn, args):
    assert fn(*args) is None


def test_single_run_ci_is_none_not_zero():
    """The specific regression: a lone run must not look like zero variance."""
    assert student_t_ci([0.42]) is None
    assert student_t_ci([0.42, 0.42]) == 0.0  # two identical runs: really zero


# ---------------------------------------------------------------------------
# 2. Consistency
# ---------------------------------------------------------------------------


def test_record_consistency_ends_and_middle():
    assert record_consistency([1.0] * 5) == 1.0  # always passes
    assert record_consistency([0.0] * 5) == 1.0  # always fails, equally consistent
    # 2 of 4 pass -> p = 0.5 -> (2*0.5 - 1)^2 = 0
    assert record_consistency([1.0, 1.0, 0.0, 0.0]) == 0.0
    # 3 of 4 pass -> p = 0.75 -> (0.5)^2 = 0.25
    assert record_consistency([1.0, 1.0, 1.0, 0.0]) == pytest.approx(0.25)


def test_record_consistency_binarises_at_the_pass_threshold():
    scores = [0.95, 0.95, 0.85, 0.85]
    assert record_consistency(scores, pass_threshold=0.9) == 0.0
    assert record_consistency(scores, pass_threshold=0.8) == 1.0


def test_outcome_consistency_skips_records_without_repeats():
    # One record with 4 repeats at p=0.75, one with a single repeat.
    got = outcome_consistency([[1.0, 1.0, 1.0, 0.0], [1.0]])
    assert got == pytest.approx(0.25)  # the single-repeat record is skipped, not 0


def test_resource_consistency_rewards_stability():
    steady = resource_consistency({"cost_usd": [0.10, 0.10, 0.10]})
    swingy = resource_consistency({"cost_usd": [0.01, 0.10, 1.00]})
    assert steady == pytest.approx(1.0)
    assert swingy < 0.5


def test_zero_cost_local_model_is_perfectly_consistent():
    """A local model bills $0 every run. That is stability, not a 0/0 error."""
    assert resource_consistency({"cost_usd": [0.0, 0.0, 0.0, 0.0]}) == pytest.approx(1.0)


def test_resource_consistency_rejects_negative_usage():
    with pytest.raises(ValueError, match="negative"):
        resource_consistency({"cost_usd": [0.1, -0.2]})


def test_trajectory_consistency_identical_and_disjoint():
    same = [["fetch", "detect", "submit"]] * 3
    assert trajectory_consistency_dist(same) == pytest.approx(1.0)
    assert trajectory_consistency_seq(same) == pytest.approx(1.0)

    disjoint = [["fetch", "fetch"], ["plot", "plot"]]
    assert trajectory_consistency_dist(disjoint) == pytest.approx(0.0)
    assert trajectory_consistency_seq(disjoint) == pytest.approx(0.0)


def test_reordering_is_seen_by_the_sequence_metric_only():
    traces = [["fetch", "detect"], ["detect", "fetch"]]
    # Same tools, same proportions: the distributional metric cannot see it.
    assert trajectory_consistency_dist(traces) == pytest.approx(1.0)
    # Two substitutions out of length two: the ordered metric can.
    assert trajectory_consistency_seq(traces) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 3. Robustness
# ---------------------------------------------------------------------------


def test_robustness_ratio_clamps_and_guards_zero_baseline():
    assert robustness_ratio(0.4, 0.8) == pytest.approx(0.5)
    assert robustness_ratio(0.9, 0.8) == 1.0  # clamped, not a bonus
    assert robustness_ratio(0.0, 0.0) is None  # nothing to be robust about
    assert robustness_ratio(0.5, 0.0) is None


# ---------------------------------------------------------------------------
# 4. Predictability
# ---------------------------------------------------------------------------


def test_perfect_and_inverted_calibration():
    conf = [0.05, 0.05, 0.95, 0.95]
    outcomes = [0.0, 0.0, 1.0, 1.0]
    assert calibration_ece(conf, outcomes) == pytest.approx(0.95, abs=0.01)
    assert brier(conf, outcomes) == pytest.approx(1 - 0.0025, abs=1e-6)

    inverted = [1.0, 1.0, 0.0, 0.0]
    assert calibration_ece(conf, inverted) < 0.1
    assert brier(conf, inverted) < 0.2


def test_auroc_orders_successes_above_failures():
    conf = [0.9, 0.8, 0.2, 0.1]
    outcomes = [1.0, 1.0, 0.0, 0.0]
    assert auroc(conf, outcomes) == pytest.approx(1.0)
    assert auroc(conf, [0.0, 0.0, 1.0, 1.0]) == pytest.approx(0.0)


def test_auroc_ties_count_as_half():
    """A model reporting one confidence everywhere is uninformative, not wrong."""
    assert auroc([0.7] * 4, [1.0, 1.0, 0.0, 0.0]) == pytest.approx(0.5)


def test_auroc_needs_both_classes():
    assert auroc([0.9, 0.8], [1.0, 1.0]) is None
    assert auroc([0.9, 0.8], [0.0, 0.0]) is None


def test_confidence_and_outcome_lengths_must_match():
    for fn in (calibration_ece, brier, auroc):
        with pytest.raises(ValueError, match="same length"):
            fn([0.5, 0.5], [1.0])


def test_calibrated_but_uninformative_is_caught_only_by_auroc():
    """The failure mode the docstring warns about, pinned as a test.

    A model that says 0.5 on everything and is right half the time is perfectly
    calibrated and tells you nothing. ECE cannot see it; AUROC reports 0.5.
    """
    conf = [0.5] * 8
    outcomes = [1.0, 0.0] * 4
    assert calibration_ece(conf, outcomes) == pytest.approx(1.0)
    assert auroc(conf, outcomes) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 5. Integrity proportions
# ---------------------------------------------------------------------------


def test_proportion():
    assert proportion([True, True, False, False]) == pytest.approx(0.5)
    assert proportion([True] * 3) == 1.0
    assert proportion([False] * 3) == 0.0


# ---------------------------------------------------------------------------
# 6. Intervals
# ---------------------------------------------------------------------------


def test_student_t_uses_the_small_sample_multiplier():
    values = [0.4, 0.5, 0.6]
    mean = 0.5
    var = sum((v - mean) ** 2 for v in values) / 2
    se = math.sqrt(var / 3)
    assert student_t_ci(values) == pytest.approx(4.303 * se)


def test_bootstrap_ci_brackets_the_mean_and_is_reproducible():
    values = [0.1, 0.5, 0.9, 0.4, 0.6, 0.55]
    lo, hi = bootstrap_ci(values)
    assert lo <= sum(values) / len(values) <= hi
    assert bootstrap_ci(values) == bootstrap_ci(values)

    # Not asserted: that a different seed gives different bounds. On a sample
    # this small the bootstrap distribution of the mean is coarse enough that
    # the 2.5% and 97.5% percentiles often land on the same value for every
    # seed. Reproducibility is the property a published summary needs; seed
    # sensitivity is not a contract, and asserting it would be a flaky test.


def test_the_two_intervals_answer_different_questions():
    """Documented distinction, pinned so a refactor cannot quietly merge them.

    `student_t_ci` is over repeat runs of one configuration and returns a
    half-width; `bootstrap_ci` is over records in a suite and returns bounds.
    """
    values = [0.2, 0.4, 0.6, 0.8]
    half_width = student_t_ci(values)
    bounds = bootstrap_ci(values)
    assert isinstance(half_width, float)
    assert isinstance(bounds, tuple) and len(bounds) == 2
