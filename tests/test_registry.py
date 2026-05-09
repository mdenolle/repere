from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from frugalmind.registry import (
    VALID_TIERS,
    cards_by_backend,
    cards_in_tier,
    load_registry_yaml,
    sorted_by_cost,
    with_overrides,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODELS_YAML = REPO_ROOT / "config" / "models.yaml"


def test_default_models_yaml_loads_with_all_tiers_present():
    registry = load_registry_yaml(DEFAULT_MODELS_YAML)
    cards = registry.list()
    assert len(cards) >= 13
    tiers = {c.metadata["tier"] for c in cards}
    for required in VALID_TIERS:
        assert required in tiers, f"tier {required} missing from default models.yaml"


def test_default_models_yaml_has_anthropic_and_openai_cards():
    registry = load_registry_yaml(DEFAULT_MODELS_YAML)
    backends = {c.backend for c in registry.list()}
    assert "anthropic" in backends
    assert "openai" in backends
    assert "ollama" in backends


def test_cards_in_tier_filters(tmp_path):
    registry = load_registry_yaml(DEFAULT_MODELS_YAML)
    cloud = cards_in_tier(registry, "cloud")
    assert all(c.metadata["tier"] == "cloud" for c in cloud)
    assert {c.backend for c in cloud}.issubset({"anthropic", "openai"})


def test_cards_in_tier_rejects_unknown():
    registry = load_registry_yaml(DEFAULT_MODELS_YAML)
    with pytest.raises(ValueError):
        cards_in_tier(registry, "ginormous")


def test_cards_by_backend_case_insensitive():
    registry = load_registry_yaml(DEFAULT_MODELS_YAML)
    a = cards_by_backend(registry, "Anthropic")
    b = cards_by_backend(registry, "anthropic")
    assert {c.id for c in a} == {c.id for c in b}


def test_sorted_by_cost_ranks_cheapest_first(tmp_path):
    registry = load_registry_yaml(DEFAULT_MODELS_YAML)
    ranked = sorted_by_cost(registry)
    # local (free) cards should come first
    assert ranked[0].cost_per_1k_in == 0.0
    # cloud opus (expensive) should be near the end
    ids_at_end = {c.id for c in ranked[-2:]}
    assert "claude-opus-4-6" in ids_at_end


def test_invalid_tier_in_yaml_rejected(tmp_path):
    bad = {
        "schema_version": 0.1,
        "models": [
            {
                "id": "x",
                "family": "x",
                "tier": "huge",
                "context_window": 1024,
                "backend": "anthropic",
            }
        ],
    }
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError):
        load_registry_yaml(p)


def test_duplicate_id_rejected(tmp_path):
    dup = {
        "schema_version": 0.1,
        "models": [
            {
                "id": "m",
                "family": "f",
                "tier": "small",
                "context_window": 1024,
                "backend": "ollama",
            },
            {
                "id": "m",
                "family": "f",
                "tier": "small",
                "context_window": 1024,
                "backend": "ollama",
            },
        ],
    }
    p = tmp_path / "dup.yaml"
    p.write_text(yaml.safe_dump(dup))
    with pytest.raises(ValueError):
        load_registry_yaml(p)


def test_missing_required_keys_rejected(tmp_path):
    incomplete = {
        "schema_version": 0.1,
        "models": [
            {"id": "x", "tier": "small"}  # missing family, context_window, backend
        ],
    }
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(incomplete))
    with pytest.raises(ValueError):
        load_registry_yaml(p)


def test_with_overrides_replaces_fields(tmp_path):
    registry = load_registry_yaml(DEFAULT_MODELS_YAML)
    [card, *_] = registry.list()
    overridden = with_overrides(card, cost_per_1k_in=99.0)
    assert overridden.cost_per_1k_in == 99.0
    assert card.cost_per_1k_in != 99.0  # original unchanged
    assert overridden.id == card.id
