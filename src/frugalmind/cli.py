"""Command-line helpers for local FrugalMind development."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from frugalmind_suites.sta_lta import STALTAIntentExtractionSuite

from . import EvalRunner, Generation, ModelCard, ModelRegistry


def _run_stub_eval(results_dir: Path) -> Path:
    """Run a deterministic no-provider smoke eval and write JSON output."""
    registry = ModelRegistry()
    registry.register(
        ModelCard(
            id="stub-local",
            family="stub",
            size_b=0,
            context_window=32_000,
            backend="local",
        )
    )

    suite = STALTAIntentExtractionSuite()
    first_prompt, first_gold, _ = next(iter(suite.items()))

    def factory(card: ModelCard):
        class StubAdapter:
            @property
            def card(self) -> ModelCard:
                return card

            def generate(self, prompt: str, **kwargs):
                text = json.dumps(first_gold) if prompt == first_prompt else "{}"
                return Generation(
                    text=text,
                    prompt_tokens=10,
                    output_tokens=10,
                    latency_s=0.0,
                    cost_usd=0.0,
                    model_id=card.id,
                )

            def estimate_cost(self, prompt: str, **kwargs) -> float:
                return 0.0

        return StubAdapter()

    runner = EvalRunner(
        registry=registry,
        suites=[suite],
        adapter_factory=factory,
        per_model_budget_usd=1.0,
        total_budget_usd=1.0,
    )
    [result] = runner.run_all()

    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / "stub_eval.json"
    path.write_text(json.dumps(result.__dict__, indent=2))
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FrugalMind local eval helpers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    smoke = subparsers.add_parser("smoke-eval", help="Run a deterministic stub eval")
    smoke.add_argument("--results-dir", default="results", type=Path)

    args = parser.parse_args(argv)
    if args.command == "smoke-eval":
        path = _run_stub_eval(args.results_dir)
        print(f"Wrote {path}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
