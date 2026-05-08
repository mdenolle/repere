"""Demo: run the skill-lift benchmark on three small-tier models.

Two modes:

  - Default (no flags): uses deterministic EchoAdapter stubs that simulate
    three different small-tier models. Useful for CI and for sanity-checking
    the runner without a model server.

  - --live: hits a local Ollama server at $OLLAMA_HOST (default
    http://127.0.0.1:11434) using the OpenAI-compatible /v1/chat/completions
    endpoint. Requires the listed models to be pulled locally:
        ollama pull mistral:7b
        ollama pull llama3.1:8b
        ollama pull qwen2.5:7b

The output is a Markdown-style table written to stdout plus a JSON payload at
results/demo_small_models.json.

Usage:

    python scripts/demo_small_models.py              # offline stub demo
    python scripts/demo_small_models.py --live       # hits local Ollama
    python scripts/demo_small_models.py --skill seismic-report
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from frugalmind import ModelCard  # noqa: E402
from frugalmind.adapters import EchoAdapter, OpenAICompatAdapter  # noqa: E402
from frugalmind.budget import BudgetGuard  # noqa: E402
from frugalmind.leaderboard import (  # noqa: E402
    LeaderboardRunner,
    build_skill_lift_leaderboard,
)
from frugalmind.registry import load_registry_yaml  # noqa: E402
from frugalmind.skills import SkillLoader, render_with_skill  # noqa: E402
from frugalmind_suites.sta_lta import STALTAIntentExtractionSuite  # noqa: E402


SKILLS_DIR = REPO / ".github" / "skills"
MODELS_YAML = REPO / "config" / "models.yaml"


def _stub_response_fn(model_id: str, prompt_to_gold: dict[str, dict]):
    """Same simulation policy as tests/test_three_small_models.py."""
    def _correct(prompt: str) -> str:
        for p, gold in prompt_to_gold.items():
            if p == prompt or p in prompt:
                return json.dumps(gold)
        return "{}"

    def _partial(prompt: str) -> str:
        for p, gold in prompt_to_gold.items():
            if p == prompt or p in prompt:
                return json.dumps({**gold, "starttime": "wrong", "endtime": "also-wrong"})
        return "{}"

    if model_id == "mistral:7b":
        def _resp(prompt: str) -> str:
            return _partial(prompt) if "Use the guidance" in prompt else "I am unsure."
        return _resp
    if model_id == "llama3.1:8b":
        def _resp(prompt: str) -> str:
            if "Use the guidance" in prompt:
                return _correct(prompt)
            first = next(iter(prompt_to_gold))
            return _correct(prompt) if prompt == first else _partial(prompt)
        return _resp
    return lambda prompt: _correct(prompt)


def _print_table(rows):
    cols = ["model_id", "score_none", "score_full", "lift", "cost_none_usd", "cost_full_usd"]
    widths = {c: max(len(c), max(len(_fmt(r, c)) for r in rows)) for c in cols}
    sep = "  ".join("-" * widths[c] for c in cols)
    print("  ".join(c.ljust(widths[c]) for c in cols))
    print(sep)
    for r in rows:
        print("  ".join(_fmt(r, c).ljust(widths[c]) for c in cols))


def _fmt(row, col: str) -> str:
    val = getattr(row, col)
    if isinstance(val, float):
        return f"{val:.4f}"
    return str(val)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Use local Ollama instead of stubs")
    parser.add_argument(
        "--ollama-host",
        default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        help="Ollama server URL (default $OLLAMA_HOST or http://127.0.0.1:11434)",
    )
    parser.add_argument("--skill", default="stalta-detection")
    parser.add_argument(
        "--output",
        default=REPO / "results" / "demo_small_models.json",
        type=Path,
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=["mistral:7b", "llama3.1:8b", "qwen2.5:7b"],
        help="Model IDs from config/models.yaml to include (must be 'small' tier).",
    )
    args = parser.parse_args(argv)

    suite = STALTAIntentExtractionSuite()
    skill = SkillLoader(skills_dir=SKILLS_DIR).get(args.skill)
    prompt_to_gold = {p: g for (p, g, _) in suite.items()}

    registry = load_registry_yaml(MODELS_YAML)
    cards: list[ModelCard] = []
    for mid in args.models:
        try:
            cards.append(registry.get(mid))
        except KeyError:
            print(f"WARN: model {mid!r} not in {MODELS_YAML}; skipping", file=sys.stderr)

    if not cards:
        print("No models to run.", file=sys.stderr)
        return 2

    if args.live:
        def factory(card: ModelCard):
            return OpenAICompatAdapter(
                _card=card,
                base_url=args.ollama_host,
                # Ollama doesn't require an API key
                api_key=None,
                default_max_tokens=512,
                timeout_s=180.0,
            )
    else:
        def factory(card: ModelCard):
            return EchoAdapter(
                _card=card,
                response_fn=_stub_response_fn(card.id, prompt_to_gold),
            )

    def render(prompt: str, mode: str) -> str:
        return render_with_skill(prompt, skill, mode=mode)

    guard = BudgetGuard(per_model_usd=10.0, total_usd=10.0)
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

    print(f"\nFrugalMind skill-lift demo  ({'LIVE Ollama' if args.live else 'offline stub'})")
    print(f"Suite : sta_lta.intent_extraction")
    print(f"Skill : {skill.name} {skill.version}")
    print(f"Models: {', '.join(c.id for c in cards)}\n")
    _print_table(rows)
    print()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_skill_lift_leaderboard(rows)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
