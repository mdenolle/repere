"""FrugalRouter — pick the cheapest model that meets a per-task quality floor.

This is the routing brain of FrugalMind. Given:
  - a registry of models (each with cost rates),
  - a budget guard (per-model and total caps),
  - a per-task quality floor (a min score to accept),
  - and a record of historical scores per (model_id, TaskKind),

`select_for(task_kind, prompt)` returns the cheapest adapter whose historical
quality on `task_kind` clears the floor and whose estimated cost still fits the
budget. If no model qualifies, the router can fall back to (a) the cheapest
historically-scored model, (b) the cheapest unscored model, or (c) raise.

The router does not run evals — `LeaderboardRunner` and `EvalRunner` do that
and update the score table via `update_score()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from . import Adapter, ModelCard, ModelRegistry, TaskKind
from .budget import BudgetGuard
from .registry import sorted_by_cost


class NoEligibleModelError(RuntimeError):
    """Raised when no model meets the quality floor and budget."""


@dataclass
class RoutingDecision:
    model_id: str
    estimated_cost_usd: float
    historical_score: float | None
    rationale: str
    fallback_used: bool = False


@dataclass
class FrugalRouter:
    """Pick the cheapest model that meets a task-specific quality floor."""

    registry: ModelRegistry
    budget: BudgetGuard
    adapter_factory: Callable[[ModelCard], Adapter]
    quality_floors: dict[TaskKind, float] = field(default_factory=dict)
    fallback_policy: str = "cheapest_eligible_or_unscored"
    # historical_scores[(model_id, task_kind)] -> mean score in [0, 1]
    historical_scores: dict[tuple[str, TaskKind], float] = field(default_factory=dict)
    output_tokens_assumed: int = 256

    def update_score(self, model_id: str, task_kind: TaskKind, score: float) -> None:
        # Exponential moving average if we already have a value, else set.
        key = (model_id, task_kind)
        prev = self.historical_scores.get(key)
        if prev is None:
            self.historical_scores[key] = float(score)
        else:
            self.historical_scores[key] = 0.5 * prev + 0.5 * float(score)

    def historical_score(self, model_id: str, task_kind: TaskKind) -> float | None:
        return self.historical_scores.get((model_id, task_kind))

    def candidates(
        self,
        task_kind: TaskKind,
        *,
        cards: Iterable[ModelCard] | None = None,
    ) -> list[ModelCard]:
        pool = list(cards) if cards is not None else self.registry.list()
        return sorted_by_cost(
            self.registry, output_tokens_assumed=self.output_tokens_assumed, cards=pool
        )

    def decide(
        self,
        task_kind: TaskKind,
        prompt: str,
        *,
        cards: Iterable[ModelCard] | None = None,
        max_output_tokens: int | None = None,
    ) -> RoutingDecision:
        floor = self.quality_floors.get(task_kind)
        for card in self.candidates(task_kind, cards=cards):
            adapter = self.adapter_factory(card)
            est = adapter.estimate_cost(
                prompt, max_output_tokens=max_output_tokens or self.output_tokens_assumed
            )
            if not self.budget.can_afford(card.id, est):
                continue
            score = self.historical_score(card.id, task_kind)
            if floor is None or (score is not None and score >= floor):
                return RoutingDecision(
                    model_id=card.id,
                    estimated_cost_usd=est,
                    historical_score=score,
                    rationale="cheapest model meeting quality floor"
                    if floor is not None
                    else "cheapest model (no floor configured)",
                )

        # No card cleared the floor. Apply fallback policy.
        if self.fallback_policy == "raise":
            raise NoEligibleModelError(
                f"No model with score >= {floor!r} for {task_kind} fits the budget"
            )

        if self.fallback_policy == "cheapest_eligible_or_unscored":
            # Walk again, accept any affordable model; prefer ones with any history.
            ranked = self.candidates(task_kind, cards=cards)
            with_history: list[ModelCard] = []
            without_history: list[ModelCard] = []
            for c in ranked:
                if self.historical_score(c.id, task_kind) is not None:
                    with_history.append(c)
                else:
                    without_history.append(c)
            for c in with_history + without_history:
                adapter = self.adapter_factory(c)
                est = adapter.estimate_cost(
                    prompt, max_output_tokens=max_output_tokens or self.output_tokens_assumed
                )
                if self.budget.can_afford(c.id, est):
                    return RoutingDecision(
                        model_id=c.id,
                        estimated_cost_usd=est,
                        historical_score=self.historical_score(c.id, task_kind),
                        rationale="fallback: cheapest affordable model",
                        fallback_used=True,
                    )

        raise NoEligibleModelError(
            f"No model fits the budget for {task_kind} (per-model={self.budget.per_model_usd}, "
            f"total remaining={self.budget.remaining('')[1]:.4f})"
        )

    def select_adapter(
        self,
        task_kind: TaskKind,
        prompt: str,
        *,
        cards: Iterable[ModelCard] | None = None,
        max_output_tokens: int | None = None,
    ) -> tuple[Adapter, RoutingDecision]:
        decision = self.decide(task_kind, prompt, cards=cards, max_output_tokens=max_output_tokens)
        adapter = self.adapter_factory(self.registry.get(decision.model_id))
        return adapter, decision


__all__ = [
    "FrugalRouter",
    "NoEligibleModelError",
    "RoutingDecision",
]
