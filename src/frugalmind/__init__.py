"""Core primitives for FrugalMind.

FrugalMind prototypes cost-aware, rigor-preserving evaluation and routing for
multi-agent systems. The interfaces here are intentionally small while the
repository is bootstrapping; they are sufficient for local suite development,
smoke tests, and future provider-backed evaluation runners.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class TaskKind(str, Enum):
    """High-level task categories used by suites and routers."""

    EXTRACTION = "extraction"
    CODE_GENERATION = "code_generation"
    PLOTTING = "plotting"
    REPORT_DRAFTING = "report_drafting"
    NUMERICAL_REGRESSION = "numerical_regression"
    RETRIEVAL = "retrieval"
    TRANSLATION = "translation"
    GROUNDED_QA = "grounded_qa"
    ORCHESTRATION = "orchestration"


class DenolleGroupSuite:
    """Base class for benchmark suites.

    Subclasses set ``task_kind`` (required at runtime) and the trio
    ``dataset_id``/``suite_id``/``version`` (required to export curated
    rows to the canonical JSONL format used by the leaderboard and HF).
    """

    task_kind: TaskKind
    # Identity used by the standard exporter (frugalmind.export). Suites that
    # never need export can leave these as None, but every benchmark intended
    # for the leaderboard should populate all three.
    dataset_id: str | None = None
    suite_id: str | None = None
    version: str = "v0.1"

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        raise NotImplementedError

    def export_rows(self) -> Iterable[Any]:
        """Yield :class:`frugalmind.export.BenchmarkRow` objects for curation.

        Default implementation raises so suites are forced to declare the
        scorer spec explicitly — that spec is what makes the JSONL artifact
        self-contained and shippable to Hugging Face.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement export_rows(); "
            "see frugalmind.export.BenchmarkRow"
        )


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
    """Budget-aware deterministic evaluation loop.

    Internally delegates spend tracking to :class:`frugalmind.budget.BudgetGuard`
    and per-call records to :class:`frugalmind.telemetry.JSONLTelemetry` (when
    `telemetry=` is supplied). The public constructor signature is kept stable
    for back-compat; pass `budget=` to share a guard across multiple runners.
    """

    def __init__(
        self,
        *,
        registry: ModelRegistry,
        suites: Iterable[DenolleGroupSuite],
        adapter_factory: Callable[[ModelCard], Adapter] | None = None,
        per_model_budget_usd: float = 1.0,
        total_budget_usd: float = 10.0,
        budget: Any = None,
        telemetry: Any = None,
        skill_name: str | None = None,
        skill_mode: str | None = None,
    ) -> None:
        from .budget import BudgetGuard  # local import to avoid cycles

        self.registry = registry
        self.suites = list(suites)
        self.adapter_factory = adapter_factory
        self.per_model_budget_usd = per_model_budget_usd
        self.total_budget_usd = total_budget_usd
        self.budget = (
            budget
            if budget is not None
            else BudgetGuard(
                per_model_usd=per_model_budget_usd,
                total_usd=total_budget_usd,
            )
        )
        self.telemetry = telemetry
        self.skill_name = skill_name
        self.skill_mode = skill_mode

    def run_all(self, model_ids: list[str] | None = None) -> list[EvalResult]:
        cards = [self.registry.get(mid) for mid in model_ids] if model_ids else self.registry.list()
        results: list[EvalResult] = []

        for card in cards:
            if self.adapter_factory is None:
                raise ValueError("EvalRunner requires adapter_factory for model execution")

            adapter = self.adapter_factory(card)
            completed = 0
            score_sum = 0.0
            details: list[dict[str, Any]] = []
            all_items = [item for suite in self.suites for item in suite.items()]
            spent_at_start = self.budget.spent(card.id)

            for idx, (prompt, gold, scorer) in enumerate(all_items):
                estimate = adapter.estimate_cost(prompt)
                if not self.budget.can_afford(card.id, estimate):
                    if self.telemetry is not None:
                        self.telemetry.log_event(
                            "budget_skip",
                            {"model_id": card.id, "item_index": idx, "estimate_usd": estimate},
                        )
                    break

                generation = adapter.generate(prompt)
                self.budget.record(card.id, generation.cost_usd)
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
                if self.telemetry is not None:
                    # v2 schema: log_sample(epoch=…) replaces
                    # log_generation(item_index=…). The legacy method stays
                    # available as a back-compat alias, but new code writes
                    # the Inspect-aligned shape directly.
                    self.telemetry.log_sample(
                        generation,
                        score=item_score,
                        epoch=idx,
                        skill_name=self.skill_name,
                        skill_mode=self.skill_mode,
                    )

            n_total = len(all_items)
            results.append(
                EvalResult(
                    model_id=card.id,
                    score=score_sum / n_total if n_total else 0.0,
                    n_completed=completed,
                    n_total=n_total,
                    cost_usd=self.budget.spent(card.id) - spent_at_start,
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


def __getattr__(name: str):
    """Lazy re-exports for the new modules to avoid import cycles."""
    if name in {"BudgetGuard", "BudgetExceeded"}:
        from .budget import BudgetExceeded, BudgetGuard

        return {"BudgetGuard": BudgetGuard, "BudgetExceeded": BudgetExceeded}[name]
    if name in {"AnthropicAdapter", "OpenAICompatAdapter", "EchoAdapter", "adapter_from_env"}:
        from .adapters import (
            AnthropicAdapter,
            EchoAdapter,
            OpenAICompatAdapter,
            adapter_from_env,
        )

        return {
            "AnthropicAdapter": AnthropicAdapter,
            "EchoAdapter": EchoAdapter,
            "OpenAICompatAdapter": OpenAICompatAdapter,
            "adapter_from_env": adapter_from_env,
        }[name]
    if name in {"FrugalRouter", "RoutingDecision", "NoEligibleModelError"}:
        from .router import FrugalRouter, NoEligibleModelError, RoutingDecision

        return {
            "FrugalRouter": FrugalRouter,
            "RoutingDecision": RoutingDecision,
            "NoEligibleModelError": NoEligibleModelError,
        }[name]
    if name in {"JSONLTelemetry", "read_jsonl"}:
        from .telemetry import JSONLTelemetry, read_jsonl

        return {"JSONLTelemetry": JSONLTelemetry, "read_jsonl": read_jsonl}[name]
    if name in {"SkillLoader", "SkillManifest", "Skill", "render_with_skill"}:
        from .skills import Skill, SkillLoader, SkillManifest, render_with_skill

        return {
            "SkillLoader": SkillLoader,
            "SkillManifest": SkillManifest,
            "Skill": Skill,
            "render_with_skill": render_with_skill,
        }[name]
    if name in {"LeaderboardRunner", "SkillLiftRow"}:
        from .leaderboard import LeaderboardRunner, SkillLiftRow

        return {"LeaderboardRunner": LeaderboardRunner, "SkillLiftRow": SkillLiftRow}[name]
    if name == "load_registry_yaml":
        from .registry import load_registry_yaml

        return load_registry_yaml
    raise AttributeError(f"module 'frugalmind' has no attribute {name!r}")
