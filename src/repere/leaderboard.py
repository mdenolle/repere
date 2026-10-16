"""Utilities for publishing Repère leaderboard data.

This module also hosts :class:`LeaderboardRunner`, which runs a benchmark suite
under two skill conditions (``"none"`` baseline and ``"full"`` skill-loaded)
and computes the per-model **skill lift** — the increase in score attributable
to the skill alone — alongside cost so a leaderboard can rank models by both
quality and frugality.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from dataclasses import fields as dataclass_fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repere.pareto import mark_frontier
from repere.reliability import record_consistency, student_t_ci

DEFAULT_SUITE = "sta_lta.intent_extraction"


# ---------------------------------------------------------------------------
# AstaBench-style categorical metadata for leaderboard rows
#
# Two axes determine whether two rows are comparable:
#   - openness: how the model+code is distributed.
#   - toolset:  what the agent had access to during the run.
#
# Categories track AstaBench's submission vocabulary so a future cross-bench
# comparison stays apples-to-apples. See `docs/leaderboard_conditions.md`.
# ---------------------------------------------------------------------------

VALID_OPENNESS = (
    "open-source-open-weight",  # code + weights public (e.g. Llama 3.x, Qwen)
    "open-source-closed-weight",  # open code, closed weights (rare)
    "closed-source-api",  # API-only access (Anthropic, OpenAI)
    "closed-source-ui",  # UI-only access (e.g. some web chat tools)
    "unknown",  # safe default when none of the above is asserted
)

VALID_TOOLSET = (
    "standard",  # only the tools the suite provides in state.tools
    "custom-interface",  # custom tools, but with the same capability constraints
    "custom",  # tools beyond the standard or custom-interface envelope
    "unknown",
)

DEFAULT_OPENNESS = "unknown"
DEFAULT_TOOLSET = "standard"


def _resolve_openness(value: Any) -> str:
    if value in (None, ""):
        return DEFAULT_OPENNESS
    s = str(value)
    return s if s in VALID_OPENNESS else DEFAULT_OPENNESS


def _resolve_toolset(value: Any) -> str:
    if value in (None, ""):
        return DEFAULT_TOOLSET
    s = str(value)
    return s if s in VALID_TOOLSET else DEFAULT_TOOLSET


@dataclass(frozen=True)
class ReliabilityBlock:
    """What repeated and perturbed runs say, or ``None`` where not measured.

    Every field is nullable on purpose. A board that shows a reliability number
    for a configuration that was run once would be inventing evidence, and these
    are expensive to collect: the robustness fields each need a whole extra
    phase. ``None`` renders as "not measured", never as zero.

    Definitions and provenance: ``docs/glossary.md`` and
    ``docs/ecosystem/hal_adoption.md``.
    """

    # Consistency: does it agree with itself across repeats?
    #
    # `consistency_scope` says what "agreement" was measured over, because the
    # same statistic means different things at different granularities:
    #   "record" — per item, then averaged. The quantity the literature defines.
    #   "arm"    — whether the whole suite mean cleared the floor on each run.
    #              Coarser, and all that is recoverable when a runner kept only
    #              per-run means. Reported, and labelled, rather than silently
    #              passed off as the finer measurement.
    consistency_scope: str | None = None
    consistency_outcome: float | None = None
    consistency_resource: float | None = None
    consistency_trajectory_dist: float | None = None
    consistency_trajectory_seq: float | None = None

    # Robustness: accuracy retained under a degraded environment.
    robust_fault: float | None = None
    robust_structural: float | None = None
    robust_prompt: float | None = None

    # Predictability: does its stated confidence mean anything?
    calibration_ece: float | None = None
    brier: float | None = None
    auroc: float | None = None

    # Integrity: the geoscience replacement for a generic safety axis.
    # Note the orientation split, which the glossary also states: grounding,
    # abstention and cutoff compliance are 1.0-is-good; the two *rates* are
    # 0.0-is-good and the site renders them on an inverted scale.
    integrity_grounding: float | None = None
    integrity_abstention: float | None = None
    integrity_cutoff_compliance: float | None = None
    integrity_citation_fabrication_rate: float | None = None
    integrity_overclaim_rate: float | None = None


@dataclass(frozen=True)
class LeaderboardRow:
    """One public leaderboard row, schema v0.2.

    `openness` and `toolset` follow AstaBench's submission vocabulary so two
    rows aren't compared apples-to-oranges. Default ``toolset`` is
    ``"standard"``; default ``openness`` is ``"unknown"`` and should be
    overridden via the model card's ``metadata.openness`` field.

    What changed from v0.1, and why:

    * ``score`` became ``score_mean`` + ``score_ci95`` + ``score_runs`` +
      ``n_epochs``. A point estimate from one run is not a measurement of a
      stochastic system, and ``paper/manuscript.md`` Methods has carried the
      TODO to fix that since before this schema existed.
    * ``in_tokens`` / ``out_tokens`` are recorded so a reader can re-price the
      board under a different list. Ours is pinned to prices that will move.
    * ``scoring_cost_usd`` is separate from ``cost_usd``. What it cost to score
      a run is not what the system costs to operate, and folding the two would
      corrupt the one axis this project exists to measure.
    * ``efficiency_score`` (score per dollar) is gone. It was unbounded, null
      for every zero-cost row, defined nowhere and read by nothing. The frontier
      flags answer the question it was reaching for.
    * ``quality_percent`` is gone: ``score_mean * 100`` carried no information
      the score did not, and it invited reading a percentage without its
      interval.
    """

    rank: int
    model_id: str
    agent_condition: str
    suite: str

    # Quality, as a distribution rather than a point.
    score_mean: float
    score_ci95: float | None
    score_runs: list[float]
    n_epochs: int

    # Cost, on every axis we can measure.
    cost_usd: float
    in_tokens: int | None
    out_tokens: int | None
    latency_s_mean: float | None
    latency_s_ci95: float | None
    n_tool_calls: int | None
    n_agent_steps: int | None

    n_completed: int
    n_total: int
    run_file: str

    scoring_cost_usd: float = 0.0
    openness: str = DEFAULT_OPENNESS
    toolset: str = DEFAULT_TOOLSET
    skill_name: str | None = None
    skill_version: str | None = None

    # Which phase produced this row. A run under fault injection is not
    # comparable to a clean one, so the provenance travels with the number.
    phase: str = "baseline"
    perturbation_seed: int | None = None
    fault_rate: float | None = None

    # Set by repere.pareto.mark_frontier once the whole board is assembled.
    on_frontier_cost: bool = False
    on_frontier_tokens: bool = False

    reliability: ReliabilityBlock = field(default_factory=ReliabilityBlock)

    @property
    def total_tokens(self) -> int | None:
        """Input plus output, the provider-independent cost proxy (issue #41)."""
        if self.in_tokens is None and self.out_tokens is None:
            return None
        return (self.in_tokens or 0) + (self.out_tokens or 0)


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


def _epoch_scores(result: dict[str, Any]) -> list[float]:
    """The per-epoch scores for one result, from whichever field carries them.

    Accepts both shapes so a v0.1 result file still exports: ``score_runs`` is
    the v0.2 field, ``score`` the single-run fallback. A fallback row is marked
    ``n_epochs = 1`` with a null interval, which is the honest rendering of one
    run — not a zero-width one.
    """
    runs = result.get("score_runs")
    if isinstance(runs, (list, tuple)) and runs:
        return [float(r) for r in runs]
    return [float(result.get("score_mean", result.get("score", 0.0)))]


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _reliability_from(result: dict[str, Any]) -> ReliabilityBlock:
    """Build the reliability block from whatever the runner measured.

    Unknown keys are ignored rather than raising: a runner that has not been
    taught a metric yet should produce a row without it, not fail the export.
    """
    raw = dict(result.get("reliability") or {})
    fields = {f.name for f in dataclass_fields(ReliabilityBlock)}
    block = {k: v for k, v in raw.items() if k in fields}

    # A runner that recorded per-run scores but computed no consistency still
    # carries enough for the arm-level form. Derive it rather than leaving the
    # column empty, and label the scope so it is not mistaken for the per-record
    # statistic.
    if block.get("consistency_outcome") is None:
        runs = result.get("score_runs")
        if isinstance(runs, (list, tuple)) and len(runs) >= 2:
            value = record_consistency([float(r) for r in runs])
            if value is not None:
                block["consistency_outcome"] = value
                block.setdefault("consistency_scope", "arm")
    return ReliabilityBlock(**block)


def build_leaderboard(
    results: list[dict[str, Any]],
    *,
    generated_at: str | None = None,
    source: str = "local eval results",
) -> dict[str, Any]:
    """Build the public leaderboard JSON payload from eval results.

    Emits schema v0.2: scores carry their repeats and interval, costs carry
    tokens, and each row is flagged for the dollar frontier and the token
    frontier separately, because the two disagree.
    """
    prepared = [(result, _epoch_scores(result)) for result in results]
    prepared.sort(
        key=lambda pair: (
            -(sum(pair[1]) / len(pair[1])),
            float(pair[0].get("cost_usd", 0.0)),
            str(pair[0].get("model_id", "")),
        ),
    )

    rows: list[LeaderboardRow] = []
    for rank, (result, scores) in enumerate(prepared, start=1):
        latencies = result.get("latency_s_runs")
        latencies = (
            [float(x) for x in latencies]
            if isinstance(latencies, (list, tuple)) and latencies
            else None
        )
        latency_mean = result.get("latency_s")
        rows.append(
            LeaderboardRow(
                rank=rank,
                model_id=str(result.get("model_id", "unknown")),
                agent_condition=str(result.get("agent_condition", "generic-coding-agent")),
                suite=str(result.get("suite", DEFAULT_SUITE)),
                score_mean=sum(scores) / len(scores),
                score_ci95=student_t_ci(scores),
                score_runs=scores,
                n_epochs=len(scores),
                cost_usd=float(result.get("cost_usd", 0.0)),
                scoring_cost_usd=float(result.get("scoring_cost_usd", 0.0)),
                in_tokens=_optional_int(result.get("in_tokens")),
                out_tokens=_optional_int(result.get("out_tokens")),
                latency_s_mean=(
                    sum(latencies) / len(latencies)
                    if latencies
                    else (None if latency_mean is None else float(latency_mean))
                ),
                latency_s_ci95=student_t_ci(latencies) if latencies else None,
                n_tool_calls=_optional_int(result.get("n_tool_calls")),
                n_agent_steps=_optional_int(result.get("n_agent_steps")),
                n_completed=int(result.get("n_completed", 0)),
                n_total=int(result.get("n_total", 0)),
                run_file=str(result.get("run_file", "unknown")),
                openness=_resolve_openness(result.get("openness")),
                toolset=_resolve_toolset(result.get("toolset")),
                skill_name=result.get("skill_name"),
                skill_version=result.get("skill_version"),
                phase=str(result.get("phase", "baseline")),
                perturbation_seed=_optional_int(result.get("perturbation_seed")),
                fault_rate=(
                    None if result.get("fault_rate") is None else float(result["fault_rate"])
                ),
                reliability=_reliability_from(result),
            )
        )

    payload_rows = [asdict(row) for row in rows]
    for payload_row, row in zip(payload_rows, rows, strict=True):
        payload_row["total_tokens"] = row.total_tokens

    # The frontier is computed **per suite**, and only over the baseline phase.
    #
    # Per suite because a score is only comparable within the task that produced
    # it: 1.00 on dv/v parameter choice and 1.00 on literature retrieval are not
    # the same achievement, and a single pooled hull would let an easy suite set
    # the frontier for a hard one. Baseline only because a run under fault
    # injection or paraphrase scores lower by construction, so letting it onto
    # the chart would compare a degraded run against clean ones.
    for row in payload_rows:
        row["on_frontier_cost"] = False
        row["on_frontier_tokens"] = False
    by_suite: dict[str, list[dict[str, Any]]] = {}
    for row in payload_rows:
        if row["phase"] == "baseline":
            by_suite.setdefault(row["suite"], []).append(row)
    for suite_rows in by_suite.values():
        mark_frontier(
            suite_rows,
            x_field="cost_usd",
            y_field="score_mean",
            flag_field="on_frontier_cost",
        )
        mark_frontier(
            suite_rows,
            x_field="total_tokens",
            y_field="score_mean",
            flag_field="on_frontier_tokens",
        )

    notes = [
        "Public leaderboard data may use smoke tests until private golden-set scores are approved for release."
    ]
    if not rows:
        notes.append("No eval result files were found for this export.")
    single_run = [r for r in rows if r.n_epochs < 2]
    if single_run:
        notes.append(
            f"{len(single_run)} of {len(rows)} rows come from a single run and carry no "
            "confidence interval; read their scores as point estimates."
        )

    return {
        "schema_version": "0.2",
        "generated_at": generated_at or utc_now_iso(),
        "source": source,
        "leaderboard": payload_rows,
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
    openness: str = DEFAULT_OPENNESS
    toolset: str = DEFAULT_TOOLSET


@dataclass
class LeaderboardRunner:
    """Run a suite under skill mode `none` and `full` and compute lift.

    The runner is provider-agnostic: it asks the supplied
    `adapter_factory(card)` for an adapter per model and a
    `prompt_render(prompt, mode)` callable that returns the prompt text in the
    requested skill mode. The expectation is that the caller wires
    :func:`repere.skills.render_with_skill` for the chosen skill.
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
                    # v2 schema (P2.5): log_sample(epoch=…) with the
                    # generation on key "output". The legacy
                    # log_generation alias still works for external
                    # callers, but in-tree code uses the new name.
                    self.telemetry.log_sample(
                        gen,
                        score=item_score,
                        suite=self.suite_id,
                        epoch=idx,
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
            card_openness = (
                (getattr(card, "metadata", {}) or {}).get("openness")
                if hasattr(card, "metadata")
                else None
            )
            # Skill-lift always exercises the `full` arm with the skill loaded,
            # so the row's toolset reflects that skill-rendered surface
            # ("custom-interface" in AstaBench's vocabulary), not "standard".
            # The `none` arm is the comparison baseline; the SkillLiftRow's
            # toolset attribute describes what was tested, which is the skill.
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
                    openness=_resolve_openness(card_openness),
                    toolset="custom-interface",
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
