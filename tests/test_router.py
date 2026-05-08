from __future__ import annotations

import pytest

from frugalmind import ModelCard, ModelRegistry, TaskKind
from frugalmind.adapters import EchoAdapter
from frugalmind.budget import BudgetGuard
from frugalmind.router import FrugalRouter, NoEligibleModelError


def _registry() -> ModelRegistry:
    """Three-card registry: cheap weak, mid OK, expensive strong."""
    r = ModelRegistry()
    r.register(ModelCard(
        id="cheap-weak", family="cheap", size_b=1, context_window=4096, backend="ollama",
        cost_per_1k_in=0.0, cost_per_1k_out=0.0, metadata={"tier": "nano"},
    ))
    r.register(ModelCard(
        id="mid-ok", family="mid", size_b=7, context_window=8192, backend="openai",
        cost_per_1k_in=0.001, cost_per_1k_out=0.002, metadata={"tier": "small"},
    ))
    r.register(ModelCard(
        id="strong-expensive", family="big", size_b=70, context_window=200000, backend="anthropic",
        cost_per_1k_in=0.015, cost_per_1k_out=0.075, metadata={"tier": "cloud"},
    ))
    return r


def _factory(card):
    return EchoAdapter(_card=card, response_text="ok")


def test_router_picks_cheapest_meeting_floor():
    reg = _registry()
    guard = BudgetGuard(per_model_usd=10.0, total_usd=100.0)
    router = FrugalRouter(
        registry=reg,
        budget=guard,
        adapter_factory=_factory,
        quality_floors={TaskKind.EXTRACTION: 0.7},
    )
    router.update_score("cheap-weak", TaskKind.EXTRACTION, 0.5)
    router.update_score("mid-ok", TaskKind.EXTRACTION, 0.8)
    router.update_score("strong-expensive", TaskKind.EXTRACTION, 0.95)

    decision = router.decide(TaskKind.EXTRACTION, "hello world")
    assert decision.model_id == "mid-ok"
    assert decision.fallback_used is False
    assert decision.historical_score == pytest.approx(0.8)


def test_router_falls_back_when_no_model_clears_floor():
    reg = _registry()
    guard = BudgetGuard(per_model_usd=10.0, total_usd=100.0)
    router = FrugalRouter(
        registry=reg,
        budget=guard,
        adapter_factory=_factory,
        quality_floors={TaskKind.CODE_GENERATION: 0.99},
    )
    router.update_score("cheap-weak", TaskKind.CODE_GENERATION, 0.30)
    router.update_score("mid-ok", TaskKind.CODE_GENERATION, 0.60)
    router.update_score("strong-expensive", TaskKind.CODE_GENERATION, 0.85)

    decision = router.decide(TaskKind.CODE_GENERATION, "write code")
    # cheapest with history wins on fallback
    assert decision.model_id == "cheap-weak"
    assert decision.fallback_used is True


def test_router_skips_models_that_break_budget():
    reg = _registry()
    # Tight budget that excludes the expensive model
    guard = BudgetGuard(per_model_usd=0.01, total_usd=0.10)
    router = FrugalRouter(
        registry=reg,
        budget=guard,
        adapter_factory=_factory,
        quality_floors={TaskKind.EXTRACTION: 0.5},
    )
    router.update_score("cheap-weak", TaskKind.EXTRACTION, 0.6)
    router.update_score("mid-ok", TaskKind.EXTRACTION, 0.8)
    router.update_score("strong-expensive", TaskKind.EXTRACTION, 0.99)
    decision = router.decide(TaskKind.EXTRACTION, "x" * 200)  # ~50 tokens
    assert decision.model_id == "cheap-weak"  # the only one within budget


def test_router_raises_when_fallback_policy_is_raise():
    reg = _registry()
    guard = BudgetGuard(per_model_usd=10.0, total_usd=100.0)
    router = FrugalRouter(
        registry=reg,
        budget=guard,
        adapter_factory=_factory,
        quality_floors={TaskKind.PLOTTING: 0.999},
        fallback_policy="raise",
    )
    router.update_score("cheap-weak", TaskKind.PLOTTING, 0.30)
    router.update_score("mid-ok", TaskKind.PLOTTING, 0.50)
    router.update_score("strong-expensive", TaskKind.PLOTTING, 0.80)
    with pytest.raises(NoEligibleModelError):
        router.decide(TaskKind.PLOTTING, "do plot")


def test_router_picks_cheapest_when_no_floor_configured():
    reg = _registry()
    guard = BudgetGuard(per_model_usd=10.0, total_usd=100.0)
    router = FrugalRouter(
        registry=reg,
        budget=guard,
        adapter_factory=_factory,
    )
    decision = router.decide(TaskKind.REPORT_DRAFTING, "report")
    assert decision.model_id == "cheap-weak"
    assert decision.historical_score is None


def test_update_score_does_ema_after_first_value():
    reg = _registry()
    guard = BudgetGuard(per_model_usd=10.0, total_usd=100.0)
    router = FrugalRouter(registry=reg, budget=guard, adapter_factory=_factory)
    router.update_score("mid-ok", TaskKind.EXTRACTION, 0.4)
    assert router.historical_score("mid-ok", TaskKind.EXTRACTION) == pytest.approx(0.4)
    router.update_score("mid-ok", TaskKind.EXTRACTION, 0.8)
    assert router.historical_score("mid-ok", TaskKind.EXTRACTION) == pytest.approx(0.6)


def test_select_adapter_returns_decision_and_adapter():
    reg = _registry()
    guard = BudgetGuard(per_model_usd=10.0, total_usd=100.0)
    router = FrugalRouter(
        registry=reg,
        budget=guard,
        adapter_factory=_factory,
        quality_floors={TaskKind.EXTRACTION: 0.0},
    )
    adapter, decision = router.select_adapter(TaskKind.EXTRACTION, "hello")
    assert decision.model_id == "cheap-weak"
    g = adapter.generate("hello")
    assert g.model_id == "cheap-weak"
