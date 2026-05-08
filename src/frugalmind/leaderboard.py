"""Utilities for publishing FrugalMind leaderboard data."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json


DEFAULT_SUITE = "sta_lta.intent_extraction_smoke"


@dataclass(frozen=True)
class LeaderboardRow:
    """One public leaderboard row."""

    rank: int
    model_id: str
    suite: str
    score: float
    quality_percent: float
    cost_usd: float
    n_completed: int
    n_total: int
    efficiency_score: float | None
    run_file: str


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
                suite=str(result.get("suite", DEFAULT_SUITE)),
                score=score,
                quality_percent=score * 100.0,
                cost_usd=cost,
                n_completed=int(result.get("n_completed", 0)),
                n_total=int(result.get("n_total", 0)),
                efficiency_score=efficiency,
                run_file=str(result.get("run_file", "unknown")),
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
