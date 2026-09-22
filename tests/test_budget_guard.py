from __future__ import annotations

import pytest

from repere.budget import BudgetExceeded, BudgetGuard


def test_can_afford_respects_per_model_cap():
    guard = BudgetGuard(per_model_usd=0.10, total_usd=1.00)
    assert guard.can_afford("m1", 0.05)
    guard.record("m1", 0.06)
    assert guard.can_afford("m1", 0.04)  # 0.06 + 0.04 == 0.10
    assert not guard.can_afford("m1", 0.05)


def test_can_afford_respects_total_cap():
    guard = BudgetGuard(per_model_usd=10.0, total_usd=0.20)
    guard.record("m1", 0.10)
    guard.record("m2", 0.05)
    assert guard.can_afford("m3", 0.05)
    assert not guard.can_afford("m3", 0.06)


def test_record_in_strict_mode_raises_on_overspend():
    guard = BudgetGuard(per_model_usd=0.10, total_usd=1.00, strict_record=True)
    guard.record("m1", 0.05)
    with pytest.raises(BudgetExceeded):
        guard.record("m1", 0.06)


def test_remaining_returns_per_model_and_total():
    guard = BudgetGuard(per_model_usd=1.0, total_usd=2.0)
    guard.record("m1", 0.30)
    guard.record("m2", 0.40)
    per, tot = guard.remaining("m1")
    assert per == pytest.approx(0.70)
    assert tot == pytest.approx(1.30)


def test_remaining_clamped_at_zero_when_over():
    guard = BudgetGuard(per_model_usd=0.10, total_usd=0.50)
    guard.record("m1", 0.20)  # already over per-model cap (non-strict)
    per, _ = guard.remaining("m1")
    assert per == 0.0


def test_negative_estimate_or_cost_rejected():
    guard = BudgetGuard(per_model_usd=1.0, total_usd=1.0)
    with pytest.raises(ValueError):
        guard.can_afford("m1", -0.01)
    with pytest.raises(ValueError):
        guard.record("m1", -0.01)


def test_summary_contains_per_model_and_total():
    guard = BudgetGuard(per_model_usd=1.0, total_usd=2.0)
    guard.record("m1", 0.10)
    guard.record("m2", 0.05)
    s = guard.summary()
    assert s["total_spent_usd"] == pytest.approx(0.15)
    assert s["by_model_usd"]["m1"] == pytest.approx(0.10)
    assert s["by_model_usd"]["m2"] == pytest.approx(0.05)
    assert s["per_model_usd"] == 1.0
    assert s["total_usd"] == 2.0


def test_reset_clears_or_targets_models():
    guard = BudgetGuard(per_model_usd=1.0, total_usd=2.0)
    guard.record("m1", 0.10)
    guard.record("m2", 0.05)
    guard.reset(["m1"])
    assert guard.spent("m1") == 0.0
    assert guard.spent("m2") == pytest.approx(0.05)
    assert guard.total_spent == pytest.approx(0.05)
    guard.reset()
    assert guard.total_spent == 0.0


def test_negative_caps_rejected_in_constructor():
    with pytest.raises(ValueError):
        BudgetGuard(per_model_usd=-1.0, total_usd=1.0)
    with pytest.raises(ValueError):
        BudgetGuard(per_model_usd=1.0, total_usd=-1.0)
