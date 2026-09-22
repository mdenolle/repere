"""Tests for EvalRunner's integration with BudgetGuard and Telemetry."""

from __future__ import annotations

from repere import (
    DenolleGroupSuite,
    EvalRunner,
    ModelCard,
    ModelRegistry,
    TaskKind,
)
from repere.adapters import EchoAdapter
from repere.budget import BudgetGuard
from repere.telemetry import JSONLTelemetry, read_jsonl


class _ToySuite(DenolleGroupSuite):
    """A trivial 2-item extraction suite that scores 1.0 on 'YES' and 0.0 otherwise."""

    task_kind = TaskKind.EXTRACTION

    def items(self):
        for prompt in ("first", "second"):
            yield (prompt, None, lambda out, gold: 1.0 if "YES" in out else 0.0)


def _registry() -> ModelRegistry:
    r = ModelRegistry()
    r.register(
        ModelCard(
            id="echo-yes",
            family="echo",
            size_b=1,
            context_window=2048,
            backend="ollama",
            cost_per_1k_in=0.001,
            cost_per_1k_out=0.001,
        )
    )
    return r


def test_eval_runner_uses_provided_budget_guard():
    reg = _registry()
    guard = BudgetGuard(per_model_usd=1.0, total_usd=1.0)
    runner = EvalRunner(
        registry=reg,
        suites=[_ToySuite()],
        adapter_factory=lambda c: EchoAdapter(_card=c, response_text="YES"),
        budget=guard,
    )
    [result] = runner.run_all()
    assert result.n_completed == 2
    assert result.score == 1.0
    assert guard.total_spent > 0
    assert guard.spent("echo-yes") == result.cost_usd


def test_eval_runner_stops_when_budget_blocks(tmp_path):
    reg = _registry()
    # Tight budget so first call fits, second would exceed it.
    # EchoAdapter("YES") on prompt "first" (5 chars => 1 in token) + 256 max_out * 0.001 = ~0.000257
    # actual call uses 1 in token + 1 out token = 0.000002 per call, so set budget = 0.0000015.
    guard = BudgetGuard(per_model_usd=0.000_001_5, total_usd=0.000_001_5)
    runner = EvalRunner(
        registry=reg,
        suites=[_ToySuite()],
        adapter_factory=lambda c: EchoAdapter(_card=c, response_text="YES"),
        budget=guard,
    )
    [result] = runner.run_all()
    # Adapter estimates output cost as max_output_tokens, so estimate exceeds tiny budget; nothing runs.
    assert result.n_completed == 0
    assert result.cost_usd == 0.0


def test_eval_runner_writes_telemetry(tmp_path):
    reg = _registry()
    path = tmp_path / "tel.jsonl"
    with JSONLTelemetry(path, run_metadata={"suite": "toy"}) as tel:
        runner = EvalRunner(
            registry=reg,
            suites=[_ToySuite()],
            adapter_factory=lambda c: EchoAdapter(_card=c, response_text="YES"),
            telemetry=tel,
            skill_name="my-skill",
            skill_mode="full",
        )
        runner.run_all()
    records = read_jsonl(path)
    # v2 schema (P2.5): generation records are now `type=sample` with the
    # model output on key `output`. Legacy `type=generation` records would
    # only appear from a v1 log read through read_jsonl with normalise=False.
    samples = [r for r in records if r["type"] == "sample"]
    assert len(samples) == 2
    assert all(r["skill_name"] == "my-skill" for r in samples)
    assert all(r["skill_mode"] == "full" for r in samples)
    assert all(r["score"] == 1.0 for r in samples)
    # Every sample record links back to the enclosing run.
    run_ids = {r["run_id"] for r in samples}
    assert len(run_ids) == 1


def test_back_compat_constructor_still_accepts_budget_args():
    reg = _registry()
    runner = EvalRunner(
        registry=reg,
        suites=[_ToySuite()],
        adapter_factory=lambda c: EchoAdapter(_card=c, response_text="YES"),
        per_model_budget_usd=10.0,
        total_budget_usd=10.0,
    )
    [result] = runner.run_all()
    assert result.score == 1.0
