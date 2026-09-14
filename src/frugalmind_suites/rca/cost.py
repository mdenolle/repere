"""Cost layer: frozen price map, model-pin checks, per-sample dollars.

Inspect records token usage per sample (``EvalSample.model_usage``) but not
dollars. This module prices a run against a **versioned** price map so the
number on the leaderboard does not move when the provider's list price does.

Two flags ride on every priced sample and on the run summary:

``model_unpinned``
    the requested model id is not in any price card's ``pinned_ids``, or the
    id the provider reported back differs from the requested one and is not
    itself pinned. Unpinned rows are still scored but the leaderboard renders
    them hatched (see DESIGN.md §6.3).
``cost_unverified``
    the card used has ``verified: false``. The run is priced only when
    ``allow_unverified=True``; otherwise ``cost_usd`` is ``None``.

Nothing here imports ``inspect_ai``; the input is a plain mapping in the shape
of Inspect's ``ModelUsage`` (``input_tokens``, ``output_tokens``,
``input_tokens_cache_read``, ``input_tokens_cache_write``, ``total_tokens``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import PRICES_PATH

_PER = 1_000_000.0


@dataclass(frozen=True)
class PriceCard:
    provider: str
    card_id: str
    pinned_ids: tuple[str, ...]
    input: float | None
    output: float | None
    cache_read: float | None
    cache_write: float | None
    verified: bool
    source_url: str | None
    source_date: str | None
    openness: str | None


@dataclass(frozen=True)
class PriceMap:
    version: str
    cards: tuple[PriceCard, ...]
    path: str

    def find(self, model_id: str) -> PriceCard | None:
        """Exact match on ``pinned_ids`` after stripping an Inspect provider prefix."""
        bare = _strip_provider(model_id)
        for c in self.cards:
            if bare in c.pinned_ids or model_id in c.pinned_ids:
                return c
        return None

    def local_card(self) -> PriceCard | None:
        for c in self.cards:
            if c.provider == "local":
                return c
        return None


@dataclass(frozen=True)
class Priced:
    model_requested: str
    model_reported: str | None
    card_id: str | None
    price_map_version: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float | None
    model_unpinned: bool
    cost_unverified: bool
    notes: list[str] = field(default_factory=list)


def _strip_provider(model_id: str) -> str:
    # Inspect ids look like "anthropic/claude-haiku-4-5" or "ollama/qwen2.5:7b".
    return model_id.split("/", 1)[1] if "/" in model_id else model_id


def _provider_of(model_id: str) -> str | None:
    return model_id.split("/", 1)[0] if "/" in model_id else None


def load_price_map(path: str | Path | None = None) -> PriceMap:
    p = Path(path) if path else PRICES_PATH
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if data.get("unit") != "per_million_tokens":
        raise ValueError(f"{p}: unit must be per_million_tokens")
    cards: list[PriceCard] = []
    for provider, entries in (data.get("providers") or {}).items():
        for e in entries or []:
            cards.append(
                PriceCard(
                    provider=str(provider),
                    card_id=str(e.get("card_id")),
                    pinned_ids=tuple(str(x) for x in (e.get("pinned_ids") or [])),
                    input=_opt_float(e.get("input")),
                    output=_opt_float(e.get("output")),
                    cache_read=_opt_float(e.get("cache_read")),
                    cache_write=_opt_float(e.get("cache_write")),
                    verified=bool(e.get("verified", False)),
                    source_url=e.get("source_url"),
                    source_date=str(e["source_date"]) if e.get("source_date") else None,
                    openness=e.get("openness"),
                )
            )
    return PriceMap(version=str(data.get("version")), cards=tuple(cards), path=str(p))


def _opt_float(v: Any) -> float | None:
    return None if v is None else float(v)


def price_usage(
    usage: Mapping[str, Any] | None,
    *,
    model_requested: str,
    model_reported: str | None,
    price_map: PriceMap,
    allow_unverified: bool = False,
    local_providers: tuple[str, ...] = ("ollama", "vllm", "openai-compat-local", "mockllm"),
    local_digest: str | None = None,
) -> Priced:
    """Price one sample's usage. Never raises on a missing card; flags instead.

    ``local_digest`` is the weights digest (e.g. the Ollama manifest digest)
    recorded by the runner for a local model; without it a local model is
    reported as unpinned, because a tag such as ``qwen2.5:7b`` can move.
    """
    usage = usage or {}
    it = int(usage.get("input_tokens") or 0)
    ot = int(usage.get("output_tokens") or 0)
    cr = int(usage.get("input_tokens_cache_read") or 0)
    cw = int(usage.get("input_tokens_cache_write") or 0)
    notes: list[str] = []

    card = price_map.find(model_requested)
    provider = _provider_of(model_requested)
    if card is None and provider in local_providers:
        card = price_map.local_card()
        notes.append(f"provider {provider!r} priced with the local (0 USD) card")

    unpinned = card is None or not card.pinned_ids and provider not in local_providers
    if card is not None and card.pinned_ids:
        req = _strip_provider(model_requested)
        rep = _strip_provider(model_reported) if model_reported else None
        if rep and rep != req and rep not in card.pinned_ids:
            unpinned = True
            notes.append(f"provider reported {rep!r} for requested {req!r}; not in pinned_ids")
    if provider in local_providers and card is not None:
        # Local models are pinned only when the run recorded a weights digest.
        if local_digest:
            notes.append(f"local model pinned by digest {local_digest}")
        else:
            unpinned = True
            notes.append("local model unpinned: no weights digest recorded by the runner")

    unverified = card is None or not card.verified
    cost: float | None = None
    if card is not None and card.input is not None and card.output is not None:
        if card.verified or allow_unverified:
            cache_read_rate = card.cache_read if card.cache_read is not None else card.input
            cache_write_rate = card.cache_write if card.cache_write is not None else card.input
            cost = (
                it * card.input + ot * card.output + cr * cache_read_rate + cw * cache_write_rate
            ) / _PER
        else:
            notes.append("card is unverified; pass allow_unverified to price it")
    elif card is None:
        notes.append("no price card matches the requested model id")

    return Priced(
        model_requested=model_requested,
        model_reported=model_reported,
        card_id=card.card_id if card else None,
        price_map_version=price_map.version,
        input_tokens=it,
        output_tokens=ot,
        cache_read_tokens=cr,
        cache_write_tokens=cw,
        cost_usd=None if cost is None else round(cost, 8),
        model_unpinned=bool(unpinned),
        cost_unverified=bool(unverified),
        notes=notes,
    )


def _usage_field(u: Any, key: str) -> Any:
    """Inspect hands back pydantic ``ModelUsage`` objects; JSON logs give dicts."""
    if u is None:
        return None
    if isinstance(u, Mapping):
        return u.get(key)
    return getattr(u, key, None)


def sum_usage(
    model_usage: Mapping[str, Mapping[str, Any]] | None,
) -> tuple[str | None, dict[str, int]]:
    """Collapse Inspect's per-model usage dict for one sample.

    Returns ``(dominant_model_id, totals)``. Most samples use one model; if a
    judge or a router used a second model the totals still add up and the
    dominant id is the one with the most output tokens.
    """
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "input_tokens_cache_read": 0,
        "input_tokens_cache_write": 0,
        "total_tokens": 0,
    }
    dominant, best = None, -1
    for mid, u in (model_usage or {}).items():
        for k in totals:
            totals[k] += int(_usage_field(u, k) or 0)
        o = int(_usage_field(u, "output_tokens") or 0)
        if o > best:
            dominant, best = mid, o
    return dominant, totals


__all__ = ["PriceCard", "PriceMap", "Priced", "load_price_map", "price_usage", "sum_usage"]
