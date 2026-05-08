"""Core primitives for FrugalMind.

FrugalMind prototypes cost-aware, rigor-preserving evaluation and routing for
multi-agent systems. The interfaces here are intentionally small while the
repository is bootstrapping; they are sufficient for local suite development,
smoke tests, and future provider-backed evaluation runners.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol
import os


class TaskKind(str, Enum):
    """High-level task categories used by suites and routers."""

    EXTRACTION = "extraction"
    CODE_GENERATION = "code_generation"
    PLOTTING = "plotting"
    REPORT_DRAFTING = "report_drafting"


class DenolleGroupSuite:
    """Base class for benchmark suites."""

    task_kind: TaskKind

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        raise NotImplementedError


@dataclass(frozen=True)
class ModelCard:
    """Minimal metadata for one model backend."""

    id: str
    family: str
    size_b: float | int | None
    context_window: int
    backend: str
    cost_per_1k_in: float = 0.0
    cost_per_1k_out: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Generation:
    """One generated response plus accounting metadata."""

    text: str
    prompt_tokens: int
    output_tokens: int
    latency_s: float
    cost_usd: float
    model_id: str


@dataclass(frozen=True)
class EvalResult:
    """Aggregate score for one model over a run."""

    model_id: str
    score: float
    n_completed: int
    n_total: int
    cost_usd: float
    details: list[dict[str, Any]] = field(default_factory=list)


class Adapter(Protocol):
    """Protocol for model adapters used by `EvalRunner`."""

    @property
    def card(self) -> ModelCard: ...

    def generate(self, prompt: str, **kwargs: Any) -> Generation: ...

    def estimate_cost(self, prompt: str, **kwargs: Any) -> float: ...


class ModelRegistry:
    """Small in-memory registry for model cards."""

    def __init__(self) -> None:
        self._cards: dict[str, ModelCard] = {}

    def register(self, card: ModelCard) -> None:
        self._cards[card.id] = card

    def get(self, model_id: str) -> ModelCard:
        return self._cards[model_id]

    def list(self) -> list[ModelCard]:
        return list(self._cards.values())


class EvalRunner:
    """Budget-aware deterministic evaluation loop."""

    def __init__(
        self,
        *,
        registry: ModelRegistry,
        suites: Iterable[DenolleGroupSuite],
        adapter_factory: Callable[[ModelCard], Adapter] | None = None,
        per_model_budget_usd: float = 1.0,
        total_budget_usd: float = 10.0,
    ) -> None:
        self.registry = registry
        self.suites = list(suites)
        self.adapter_factory = adapter_factory
        self.per_model_budget_usd = per_model_budget_usd
        self.total_budget_usd = total_budget_usd

    def run_all(self, model_ids: list[str] | None = None) -> list[EvalResult]:
        cards = [self.registry.get(mid) for mid in model_ids] if model_ids else self.registry.list()
        total_spent = 0.0
        results: list[EvalResult] = []

        for card in cards:
            if self.adapter_factory is None:
                raise ValueError("EvalRunner requires adapter_factory for model execution")

            adapter = self.adapter_factory(card)
            model_spent = 0.0
            completed = 0
            score_sum = 0.0
            details: list[dict[str, Any]] = []
            all_items = [item for suite in self.suites for item in suite.items()]

            for idx, (prompt, gold, scorer) in enumerate(all_items):
                estimate = adapter.estimate_cost(prompt)
                if model_spent + estimate > self.per_model_budget_usd:
                    break
                if total_spent + estimate > self.total_budget_usd:
                    break

                generation = adapter.generate(prompt)
                model_spent += generation.cost_usd
                total_spent += generation.cost_usd
                item_score = float(scorer(generation.text, gold))
                completed += 1
                score_sum += item_score
                details.append(
                    {
                        "item_index": idx,
                        "score": item_score,
                        "cost_usd": generation.cost_usd,
                        "model_id": generation.model_id,
                    }
                )

            n_total = len(all_items)
            results.append(
                EvalResult(
                    model_id=card.id,
                    score=score_sum / n_total if n_total else 0.0,
                    n_completed=completed,
                    n_total=n_total,
                    cost_usd=model_spent,
                    details=details,
                )
            )

        return results


def load_env_keys(env_file: str | os.PathLike[str] = ".env") -> None:
    """Load simple KEY=VALUE pairs from a local env file if one exists."""

    path = Path(env_file)
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


__all__ = [
    "Adapter",
    "DenolleGroupSuite",
    "EvalResult",
    "EvalRunner",
    "Generation",
    "ModelCard",
    "ModelRegistry",
    "TaskKind",
    "load_env_keys",
]
