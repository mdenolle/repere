"""Utilities for publishing FrugalMind leaderboard data.

This module also hosts :class:`LeaderboardRunner`, which runs a benchmark suite
under two skill conditions (``"none"`` baseline and ``"full"`` skill-loaded)
and computes the per-model **skill lift** — the increase in score attributable
to the skill alone — alongside cost so a leaderboard can rank models by both
quality and frugality.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
import json


DEFAULT_SUITE = "sta_lta.intent_extraction"


@dataclass(frozen=True)
class LeaderboardRow:
    """One public leaderboard row."""

    rank: int
    model_id: str
    agent_condition: str
    suite: str
    score: float
    quality_percent: float
    cost_usd: float
    n_completed: int
    n_total: int
    efficiency_score: float | None
    run_file: str
    skill_name: str | None = None
    skill_version: str | None = None


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_result(payload: dict[str, Any], run_file: str) -> list[dict[str, Any]]:
    if "results" in payload and isinstance(payload["results"], list):
        results = payload["results"]
    else:
        results = [payload]

    suite = payload.get("suite", DEFAULT_SUITE)
    rows = []
    for result in results:
        if not isinstance(result, dict) or "model_id" not in result:
            continue
        row = dict(result)
        row.setdefault("suite", suite)
        row.setdefault("run_file", run_file)
        rows.append(row)
    return rows


def load_eval_results(results_dir: Path) -> list[dict[str, Any]]:
    """Load eval result JSON files from a results directory."""
    if not results_dir.exists():
        return []

    loaded: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        loaded.extend(_coerce_result(payload, path.name))
    return loaded


def build_leaderboard(
    results: list[dict[str, Any]],
    *,
    generated_at: str | None = None,
    source: str = "local eval results",
) -> dict[str, Any]:
    """Build the public leaderboard JSON payload from eval results."""
    sorted_results = sorted(
        results,
        key=lambda item: (
            -float(item.get("score", 0.0)),
            float(item.get("cost_usd", 0.0)),
            str(item.get("model_id", "")),
        ),
    )

    rows: list[LeaderboardRow] = []
    for rank, result in enumerate(sorted_results, start=1):
        score = float(result.get("score", 0.0))
        cost = float(result.get("cost_usd", 0.0))
        efficiency = score / cost if cost > 0 else None
        rows.append(
            LeaderboardRow(
                rank=rank,
                model_id=str(result.get("model_id", "unknown")),
                agent_condition=str(result.get("agent_condition", "generic-coding-agent")),
                suite=str(result.get("suite", DEFAULT_SUITE)),
                score=score,
                quality_percent=score * 100.0,
                cost_usd=cost,
                n_completed=int(result.get("n_completed", 0)),
                n_total=int(result.get("n_total", 0)),
                efficiency_score=efficiency,
                run_file=str(result.get("run_file", "unknown")),
                skill_name=result.get("skill_name"),
                skill_version=result.get("skill_version"),
            )
        )

    notes = [
        "Public leaderboard data may use smoke tests until private golden-set scores are approved for release."
    ]
    if not rows:
        notes.append("No eval result files were found for this export.")

    return {
        "schema_version": "0.1",
        "generated_at": generated_at or utc_now_iso(),
        "source": source,
        "leaderboard": [asdict(row) for row in rows],
        "notes": notes,
    }


def export_leaderboard(results_dir: Path, output_path: Path) -> Path:
    """Export leaderboard JSON from result files."""
    payload = build_leaderboard(load_eval_results(results_dir), source=str(results_dir))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n")
    return output_path


# ---------------------------------------------------------------------------
# LeaderboardRunner: skill-lift benchmark
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillLiftRow:
    """One row of a skill-lift leaderboard.

    `lift` is `score_full - score_none`: the increase in deterministic score
    attributable to enabling the skill. `cost_lift_pct` is the ratio
    `(cost_full - cost_none) / cost_none` (or `None` when cost is zero, e.g.,
    purely local models).
    """

    model_id: str
    suite: str
    skill_name: str
    skill_version: str
    score_none: float
    score_full: float
    lift: float
    cost_none_usd: float
    cost_full_usd: float
    cost_lift_pct: float | None
    n_total: int


@dataclass
class LeaderboardRunner:
    """Run a suite under skill mode `none` and `full` and compute lift.

    The runner is provider-agnostic: it asks the supplied
    `adapter_factory(card)` for an adapter per model and a
    `prompt_render(prompt, mode)` callable that returns the prompt text in the
    requested skill mode. The expectation is that the caller wires
    :func:`frugalmind.skills.render_with_skill` for the chosen skill.
    """

    suite: Any
    suite_id: str
    skill_name: str
    skill_version: str
    adapter_factory: Callable[[Any], Any]
    prompt_render: Callable[[str, str], str]
    budget: Any | None = None
    telemetry: Any | None = None

    def run_one_model(self, card: Any) -> dict[str, dict[str, float | int]]:
        """Run the suite for one model under both skill modes.

        Returns ``{"none": {...}, "full": {...}}`` with score, cost, and n.
        """
        from .budget import BudgetGuard  # local import to avoid cycles

        out: dict[str, dict[str, float | int]] = {}
        adapter = self.adapter_factory(card)
        for mode in ("none", "full"):
            score_sum = 0.0
            cost_sum = 0.0
            count = 0
            items = list(self.suite.items())
            for idx, (prompt, gold, scorer) in enumerate(items):
                rendered = self.prompt_render(prompt, mode)
                if self.budget is not None:
                    est = adapter.estimate_cost(rendered)
                    if not self.budget.can_afford(card.id, est):
                        break
                gen = adapter.generate(rendered)
                if self.budget is not None:
                    self.budget.record(card.id, gen.cost_usd)
                cost_sum += gen.cost_usd
                item_score = float(scorer(gen.text, gold))
                score_sum += item_score
                count += 1
                if self.telemetry is not None:
                    self.telemetry.log_generation(
                        gen,
                        score=item_score,
                        suite=self.suite_id,
                        item_index=idx,
                        skill_name=self.skill_name,
                        skill_mode=mode,
                    )
            n_total = len(items)
            out[mode] = {
                "score": score_sum / n_total if n_total else 0.0,
                "cost_usd": cost_sum,
                "n_completed": count,
                "n_total": n_total,
            }
        return out

    def run(self, cards: Iterable[Any]) -> list[SkillLiftRow]:
        rows: list[SkillLiftRow] = []
        for card in cards:
            r = self.run_one_model(card)
            none = r["none"]
            full = r["full"]
            cost_none = float(none["cost_usd"])
            cost_full = float(full["cost_usd"])
            cost_lift_pct: float | None
            if cost_none > 0:
                cost_lift_pct = (cost_full - cost_none) / cost_none * 100.0
            else:
                cost_lift_pct = None
            rows.append(
                SkillLiftRow(
                    model_id=str(card.id),
                    suite=self.suite_id,
                    skill_name=self.skill_name,
                    skill_version=self.skill_version,
                    score_none=float(none["score"]),
                    score_full=float(full["score"]),
                    lift=float(full["score"]) - float(none["score"]),
                    cost_none_usd=cost_none,
                    cost_full_usd=cost_full,
                    cost_lift_pct=cost_lift_pct,
                    n_total=int(none["n_total"]),
                )
            )
        return rows


def build_skill_lift_leaderboard(
    rows: list[SkillLiftRow],
    *,
    generated_at: str | None = None,
    source: str = "skill-lift run",
) -> dict[str, Any]:
    """Build a JSON payload for skill-lift leaderboard publication."""
    sorted_rows = sorted(rows, key=lambda r: (-r.lift, r.cost_full_usd, r.model_id))
    notes = [
        "Skill-lift leaderboard: each row reports the same model on the same "
        "suite under skill_mode='none' (baseline) and skill_mode='full' "
        "(skill loaded). 'lift' = score_full - score_none."
    ]
    if not sorted_rows:
        notes.append("No skill-lift rows for this export.")
    return {
        "schema_version": "0.1",
        "generated_at": generated_at or utc_now_iso(),
        "source": source,
        "leaderboard_kind": "skill_lift",
        "rows": [asdict(r) for r in sorted_rows],
        "notes": notes,
    }


def export_skill_lift_leaderboard(
    rows: list[SkillLiftRow],
    output_path: Path,
    *,
    generated_at: str | None = None,
) -> Path:
    payload = build_skill_lift_leaderboard(rows, generated_at=generated_at)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n")
    return output_path


__all__ = [
    "DEFAULT_SUITE",
    "LeaderboardRow",
    "LeaderboardRunner",
    "SkillLiftRow",
    "build_leaderboard",
    "build_skill_lift_leaderboard",
    "export_leaderboard",
    "export_skill_lift_leaderboard",
    "load_eval_results",
    "utc_now_iso",
]
