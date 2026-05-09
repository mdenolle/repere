"""LeaderboardRunner: skill-lift benchmark integration tests."""

from __future__ import annotations

import json

from frugalmind import DenolleGroupSuite, ModelCard, ModelRegistry, TaskKind
from frugalmind.adapters import EchoAdapter
from frugalmind.budget import BudgetGuard
from frugalmind.leaderboard import (
    LeaderboardRunner,
    build_skill_lift_leaderboard,
    export_skill_lift_leaderboard,
)


class _SkillSensitiveSuite(DenolleGroupSuite):
    """Two-item suite that scores 1.0 only when prompt contains GUIDANCE."""

    task_kind = TaskKind.EXTRACTION

    def items(self):
        for prompt in ("first", "second"):
            yield (prompt, None, lambda out, gold: 1.0 if "INSIGHT" in out else 0.0)


def _registry() -> ModelRegistry:
    r = ModelRegistry()
    # cheap (free) and expensive
    r.register(
        ModelCard(
            id="local-7b",
            family="local",
            size_b=7,
            context_window=8192,
            backend="ollama",
            cost_per_1k_in=0.0,
            cost_per_1k_out=0.0,
        )
    )
    r.register(
        ModelCard(
            id="cloud-frontier",
            family="cloud",
            size_b=None,
            context_window=200000,
            backend="anthropic",
            cost_per_1k_in=0.015,
            cost_per_1k_out=0.075,
        )
    )
    return r


def _factory_for(card):
    """Adapter behaviour: respond INSIGHT only when prompt contains 'GUIDANCE'."""

    def _resp(prompt):
        return "INSIGHT" if "GUIDANCE" in prompt else "no idea"

    return EchoAdapter(_card=card, response_fn=_resp)


def _render(prompt: str, mode: str) -> str:
    """Mimic skill loader: full mode prepends GUIDANCE, none mode doesn't."""
    if mode == "full":
        return f"GUIDANCE: be insightful.\n\nTask:\n{prompt}"
    return prompt


def test_skill_lift_runner_computes_lift_and_cost_delta():
    reg = _registry()
    suite = _SkillSensitiveSuite()
    runner = LeaderboardRunner(
        suite=suite,
        suite_id="toy.skill_sensitive",
        skill_name="toy-skill",
        skill_version="v0.1",
        adapter_factory=_factory_for,
        prompt_render=_render,
    )
    rows = runner.run(reg.list())
    by_id = {r.model_id: r for r in rows}
    # Both models go from 0 → 1 when GUIDANCE is added.
    for model_id in ("local-7b", "cloud-frontier"):
        r = by_id[model_id]
        assert r.score_none == 0.0
        assert r.score_full == 1.0
        assert r.lift == 1.0
        assert r.suite == "toy.skill_sensitive"
        assert r.skill_name == "toy-skill"
    # Cost: free model has no lift_pct
    assert by_id["local-7b"].cost_lift_pct is None
    # Paid model: full mode prompts longer, so cost_full > cost_none
    assert by_id["cloud-frontier"].cost_full_usd > by_id["cloud-frontier"].cost_none_usd
    assert by_id["cloud-frontier"].cost_lift_pct is not None
    assert by_id["cloud-frontier"].cost_lift_pct > 0


def test_skill_lift_runner_respects_budget():
    reg = _registry()
    suite = _SkillSensitiveSuite()
    # Tight budget: each call ~0.0019 USD per item; allow only 1 item per mode for cloud
    guard = BudgetGuard(per_model_usd=10.0, total_usd=10.0)
    runner = LeaderboardRunner(
        suite=suite,
        suite_id="toy",
        skill_name="toy-skill",
        skill_version="v0.1",
        adapter_factory=_factory_for,
        prompt_render=_render,
        budget=guard,
    )
    rows = runner.run(reg.list())
    by_id = {r.model_id: r for r in rows}
    assert by_id["cloud-frontier"].cost_full_usd > 0
    assert guard.total_spent > 0


def test_export_skill_lift_leaderboard_writes_json(tmp_path):
    reg = _registry()
    suite = _SkillSensitiveSuite()
    runner = LeaderboardRunner(
        suite=suite,
        suite_id="toy",
        skill_name="toy-skill",
        skill_version="v0.1",
        adapter_factory=_factory_for,
        prompt_render=_render,
    )
    rows = runner.run(reg.list())
    output = tmp_path / "skill_lift.json"
    export_skill_lift_leaderboard(rows, output, generated_at="2026-05-08T00:00:00Z")
    payload = json.loads(output.read_text())
    assert payload["leaderboard_kind"] == "skill_lift"
    assert payload["generated_at"] == "2026-05-08T00:00:00Z"
    assert len(payload["rows"]) == 2
    # Ranked by lift desc, then cost_full asc
    assert {r["model_id"] for r in payload["rows"]} == {"local-7b", "cloud-frontier"}


def test_build_skill_lift_leaderboard_handles_no_rows():
    payload = build_skill_lift_leaderboard([])
    assert payload["leaderboard_kind"] == "skill_lift"
    assert payload["rows"] == []
    assert any("No skill-lift rows" in n for n in payload["notes"])
