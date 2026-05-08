"""Smoke test that the lazy re-exports on `frugalmind` resolve correctly."""

from __future__ import annotations


def test_lazy_exports_resolve():
    import frugalmind as F

    assert F.BudgetGuard is not None
    assert F.AnthropicAdapter is not None
    assert F.OpenAICompatAdapter is not None
    assert F.EchoAdapter is not None
    assert F.FrugalRouter is not None
    assert F.JSONLTelemetry is not None
    assert F.SkillLoader is not None
    assert F.SkillManifest is not None
    assert F.LeaderboardRunner is not None
    assert F.load_registry_yaml is not None


def test_lazy_export_unknown_attribute_raises():
    import frugalmind as F
    import pytest

    with pytest.raises(AttributeError):
        F.NotARealThing  # noqa: B018
