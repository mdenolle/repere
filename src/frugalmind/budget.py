"""Budget enforcement for FrugalMind eval runs.

`BudgetGuard` tracks spend per model and overall, decides whether a candidate
call fits within the configured caps, and records actual spend. Separating it
from `EvalRunner` lets routers, leaderboard runners, and CLI tools share one
budget across multiple suites.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


class BudgetExceeded(RuntimeError):
    """Raised when an attempted record() pushes spend past a configured cap."""


@dataclass
class BudgetGuard:
    """Per-model and total USD budget tracker.

    Behaviour:
      - `can_afford(model_id, estimate_usd)` is non-mutating and returns True only
        if recording `estimate_usd` would not exceed the per-model or total cap.
      - `record(model_id, cost_usd)` mutates spend; raises `BudgetExceeded` when
        `strict_record=True` and a cap is crossed.
      - `remaining(model_id)` returns `(per_model_remaining, total_remaining)`.
      - `summary()` returns a JSON-serializable dict of current spend.
    """

    per_model_usd: float
    total_usd: float
    strict_record: bool = False
    _spend_by_model: dict[str, float] = field(default_factory=dict)
    _total_spent: float = 0.0

    def __post_init__(self) -> None:
        if self.per_model_usd < 0 or self.total_usd < 0:
            raise ValueError("Budget caps must be non-negative")

    @property
    def total_spent(self) -> float:
        return self._total_spent

    def spent(self, model_id: str) -> float:
        return self._spend_by_model.get(model_id, 0.0)

    def can_afford(self, model_id: str, estimate_usd: float) -> bool:
        if estimate_usd < 0:
            raise ValueError("estimate_usd must be non-negative")
        if self._spend_by_model.get(model_id, 0.0) + estimate_usd > self.per_model_usd:
            return False
        if self._total_spent + estimate_usd > self.total_usd:
            return False
        return True

    def record(self, model_id: str, cost_usd: float) -> None:
        if cost_usd < 0:
            raise ValueError("cost_usd must be non-negative")
        new_model_spend = self._spend_by_model.get(model_id, 0.0) + cost_usd
        new_total_spend = self._total_spent + cost_usd
        if self.strict_record:
            if new_model_spend > self.per_model_usd:
                raise BudgetExceeded(
                    f"Per-model budget {self.per_model_usd:.4f} exceeded for {model_id!r} "
                    f"(would spend {new_model_spend:.4f})"
                )
            if new_total_spend > self.total_usd:
                raise BudgetExceeded(
                    f"Total budget {self.total_usd:.4f} exceeded "
                    f"(would spend {new_total_spend:.4f})"
                )
        self._spend_by_model[model_id] = new_model_spend
        self._total_spent = new_total_spend

    def remaining(self, model_id: str) -> tuple[float, float]:
        per = max(0.0, self.per_model_usd - self._spend_by_model.get(model_id, 0.0))
        tot = max(0.0, self.total_usd - self._total_spent)
        return per, tot

    def reset(self, model_ids: Iterable[str] | None = None) -> None:
        if model_ids is None:
            self._spend_by_model.clear()
            self._total_spent = 0.0
            return
        for mid in model_ids:
            removed = self._spend_by_model.pop(mid, 0.0)
            self._total_spent = max(0.0, self._total_spent - removed)

    def summary(self) -> dict:
        return {
            "per_model_usd": self.per_model_usd,
            "total_usd": self.total_usd,
            "total_spent_usd": round(self._total_spent, 6),
            "by_model_usd": {k: round(v, 6) for k, v in self._spend_by_model.items()},
        }


__all__ = ["BudgetExceeded", "BudgetGuard"]
