"""Model registry helpers — load YAML into ModelCards, filter by size_band."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

import yaml

from . import ModelCard, ModelRegistry


VALID_SIZE_BANDS = ("nano", "small", "medium", "big", "cloud")


def _coerce_card(entry: dict[str, Any]) -> tuple[ModelCard, str]:
    """Translate a YAML entry into a ModelCard plus its size_band."""
    required = ("id", "family", "context_window", "backend")
    missing = [k for k in required if k not in entry]
    if missing:
        raise ValueError(f"models.yaml entry missing keys {missing!r}: {entry.get('id')}")

    size_band = entry.get("size_band")
    if size_band is None or size_band not in VALID_SIZE_BANDS:
        raise ValueError(
            f"models.yaml entry {entry['id']!r} has invalid size_band {size_band!r}; "
            f"valid size bands: {VALID_SIZE_BANDS}"
        )

    metadata = dict(entry.get("metadata") or {})
    metadata.setdefault("size_band", size_band)

    card = ModelCard(
        id=str(entry["id"]),
        family=str(entry["family"]),
        size_b=entry.get("size_b"),
        context_window=int(entry["context_window"]),
        backend=str(entry["backend"]),
        cost_per_1k_in=float(entry.get("cost_per_1k_in", 0.0)),
        cost_per_1k_out=float(entry.get("cost_per_1k_out", 0.0)),
        metadata=metadata,
    )
    return card, size_band


def load_registry_yaml(path: str | Path) -> ModelRegistry:
    """Load a `models.yaml` file into a `ModelRegistry`.

    Each card's size_band is preserved on `card.metadata['size_band']`.
    """
    p = Path(path)
    with open(p) as f:
        data = yaml.safe_load(f) or {}

    raw_models = data.get("models") or []
    if not isinstance(raw_models, list):
        raise ValueError("models.yaml must contain a top-level `models:` list")

    registry = ModelRegistry()
    seen: set[str] = set()
    for entry in raw_models:
        if not isinstance(entry, dict):
            raise ValueError(f"models.yaml entry must be a mapping, got {type(entry)!r}")
        card, _ = _coerce_card(entry)
        if card.id in seen:
            raise ValueError(f"Duplicate model id {card.id!r} in {p}")
        seen.add(card.id)
        registry.register(card)
    return registry


def cards_in_size_band(registry: ModelRegistry, size_band: str) -> list[ModelCard]:
    if size_band not in VALID_SIZE_BANDS:
        raise ValueError(f"Unknown size band {size_band!r}; valid: {VALID_SIZE_BANDS}")
    return [c for c in registry.list() if c.metadata.get("size_band") == size_band]


def cards_by_backend(registry: ModelRegistry, backend: str) -> list[ModelCard]:
    return [c for c in registry.list() if c.backend.lower() == backend.lower()]


def sorted_by_cost(
    registry: ModelRegistry,
    *,
    output_tokens_assumed: int = 256,
    input_tokens_assumed: int = 512,
    cards: Iterable[ModelCard] | None = None,
) -> list[ModelCard]:
    """Return cards ordered by an estimated unit-call cost (cheapest first)."""
    pool = list(cards) if cards is not None else registry.list()

    def _est(c: ModelCard) -> float:
        return (
            input_tokens_assumed / 1000.0 * c.cost_per_1k_in
            + output_tokens_assumed / 1000.0 * c.cost_per_1k_out
        )

    return sorted(pool, key=lambda c: (_est(c), c.id))


def with_overrides(card: ModelCard, **overrides: Any) -> ModelCard:
    """Return a copy of `card` with the given fields replaced (frozen-safe)."""
    return replace(card, **overrides)


__all__ = [
    "VALID_SIZE_BANDS",
    "cards_by_backend",
    "cards_in_size_band",
    "load_registry_yaml",
    "sorted_by_cost",
    "with_overrides",
]
