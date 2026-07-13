"""End-to-end check: 3 small-tier models from config/models.yaml run through
the skill-lift benchmark on the public STA/LTA intent suite.

Uses EchoAdapter so the test is deterministic and provider-free. Each model is
given a different fake response policy so the assertions verify the runner is
actually calling per-model adapters and emitting per-model rows.

For a live run against real Ollama models, see scripts/demo_small_models.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from frugalmind import ModelCard, ModelRegistry
from frugalmind.adapters import EchoAdapter
from frugalmind.budget import BudgetGuard
from frugalmind.leaderboard import LeaderboardRunner, build_skill_lift_leaderboard
from frugalmind.registry import cards_in_tier, load_registry_yaml
from frugalmind.skills import SkillLoader, render_with_skill
from frugalmind_suites.sta_lta import STALTAIntentExtractionSuite


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / ".github" / "skills"
MODELS_YAML = REPO_ROOT / "config" / "models.yaml"


def _build_prompt_to_gold(suite) -> dict[str, dict]:
    """Walk the suite once to build a {prompt -> gold} lookup the fake
    adapters can use to produce per-item correct or partial answers."""
    return {prompt: gold for (prompt, gold, _scorer) in suite.items()}


def _model_response_fn(model_id: str, prompt_to_gold: dict[str, dict]):
    """Return a fake adapter response policy that varies per model.

    - mistral:7b   — broken without skill. Partial credit with skill (right
                     station/channel, garbled times).
    - llama3.1:8b  — partial without skill (gets first item right, others
                     close-but-wrong). Fully correct with skill.
    - qwen2.5:7b   — strong baseline. Correct in both modes; lift ≈ 0.
    """

    def _correct_for(prompt: str) -> str:
        # Rebuild the gold for the matching item (or fall back to the first).
        for p, gold in prompt_to_gold.items():
            if p == prompt or p in prompt:
                return json.dumps(gold)
        return json.dumps(next(iter(prompt_to_gold.values())))

    def _partial_for(prompt: str) -> str:
        # Right station fields; deliberately wrong times → ~4/6 fields match.
        for p, gold in prompt_to_gold.items():
            if p == prompt or p in prompt:
                broken = {**gold, "starttime": "wrong", "endtime": "also-wrong"}
                return json.dumps(broken)
        return "{}"

    def _broken() -> str:
        return "I am not sure how to answer this."

    if model_id == "mistral:7b":

        def _resp(prompt: str) -> str:
            if "Use the guidance" in prompt:
                return _partial_for(prompt)
            return _broken()

        return _resp

    if model_id == "llama3.1:8b":

        def _resp(prompt: str) -> str:
            if "Use the guidance" in prompt:
                return _correct_for(prompt)
            # Without skill: only the first item is right; others partial.
            first_prompt = next(iter(prompt_to_gold))
            if prompt == first_prompt:
                return _correct_for(prompt)
            return _partial_for(prompt)

        return _resp

    # qwen2.5:7b: strong baseline.
    def _resp(prompt: str) -> str:
        return _correct_for(prompt)

    return _resp


def _three_small_cards() -> list[ModelCard]:
    """Pick three small-tier cards by id; if any are missing, take the first three small."""
    registry = load_registry_yaml(MODELS_YAML)
    preferred = ["mistral:7b", "llama3.1:8b", "qwen2.5:7b"]
    picked: list[ModelCard] = []
    for mid in preferred:
        try:
            picked.append(registry.get(mid))
        except KeyError:
            continue
    if len(picked) < 3:
        for c in cards_in_tier(registry, "small"):
            if c.id not in {p.id for p in picked}:
                picked.append(c)
            if len(picked) >= 3:
                break
    assert len(picked) == 3, f"expected 3 small-tier cards, got {len(picked)}"
    return picked


def test_three_small_models_run_skill_lift_benchmark():
    cards = _three_small_cards()
    suite = STALTAIntentExtractionSuite()
    skill = SkillLoader(skills_dir=SKILLS_DIR).get("stalta-detection")
    guard = BudgetGuard(per_model_usd=10.0, total_usd=10.0)

    prompt_to_gold = _build_prompt_to_gold(suite)

    def factory(card: ModelCard) -> EchoAdapter:
        return EchoAdapter(_card=card, response_fn=_model_response_fn(card.id, prompt_to_gold))

    def render(prompt: str, mode: str) -> str:
        return render_with_skill(prompt, skill, mode=mode)

    runner = LeaderboardRunner(
        suite=suite,
        suite_id="sta_lta.intent_extraction",
        skill_name=skill.name,
        skill_version=skill.version,
        adapter_factory=factory,
        prompt_render=render,
        budget=guard,
    )
    rows = runner.run(cards)

    # Three rows, one per model.
    assert len(rows) == 3
    by_id = {r.model_id: r for r in rows}
    assert {"mistral:7b", "llama3.1:8b", "qwen2.5:7b"} == set(by_id)

    # Calibrated assertions per fake adapter policy:
    # - mistral:7b: 0 baseline → some skill lift (partial credit)
    assert by_id["mistral:7b"].score_none == 0.0
    assert by_id["mistral:7b"].score_full > 0.0
    assert by_id["mistral:7b"].lift > 0.0

    # - llama3.1:8b: low baseline → strong skill lift to ~1.0
    assert by_id["llama3.1:8b"].score_none < by_id["llama3.1:8b"].score_full
    assert by_id["llama3.1:8b"].lift > 0.0

    # - qwen2.5:7b: strong baseline already; lift is ~0
    assert by_id["qwen2.5:7b"].score_none == 1.0
    assert by_id["qwen2.5:7b"].lift == 0.0

    # All three have the right metadata for leaderboard publication.
    for r in rows:
        assert r.suite == "sta_lta.intent_extraction"
        assert r.skill_name == "stalta-detection"
        assert r.skill_version == "v0.3"
        assert r.n_total == len(list(suite.items()))


def test_three_small_models_skill_lift_payload_ranks_by_lift():
    cards = _three_small_cards()
    suite = STALTAIntentExtractionSuite()
    skill = SkillLoader(skills_dir=SKILLS_DIR).get("stalta-detection")

    prompt_to_gold = _build_prompt_to_gold(suite)

    def factory(card: ModelCard) -> EchoAdapter:
        return EchoAdapter(_card=card, response_fn=_model_response_fn(card.id, prompt_to_gold))

    def render(prompt: str, mode: str) -> str:
        return render_with_skill(prompt, skill, mode=mode)

    runner = LeaderboardRunner(
        suite=suite,
        suite_id="sta_lta.intent_extraction",
        skill_name=skill.name,
        skill_version=skill.version,
        adapter_factory=factory,
        prompt_render=render,
    )
    rows = runner.run(cards)
    payload = build_skill_lift_leaderboard(rows, generated_at="2026-05-08T00:00:00Z")
    ranked_ids = [r["model_id"] for r in payload["rows"]]
    # The two models with non-zero lift should rank above the qwen baseline.
    assert ranked_ids.index("qwen2.5:7b") == len(ranked_ids) - 1
    assert payload["leaderboard_kind"] == "skill_lift"
    assert payload["generated_at"] == "2026-05-08T00:00:00Z"
