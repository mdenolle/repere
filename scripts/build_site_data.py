"""Refresh `site/data/leaderboard.json` and `site/data/skill_lift.json`.

This script reads:

  - `results/*.json` produced by `frugalmind smoke-eval` and
    `frugalmind run-ollama-intent` (regular per-row eval results).
  - `results/demo_small_models.json` produced by `scripts/demo_small_models.py`
    (skill-lift output: one record per model with both `none` and `full`
    conditions).

It writes:

  - `site/data/leaderboard.json` — combined leaderboard rows. Each skill-lift
    record contributes two rows (one per condition) so the existing HTML
    table can render the full set unchanged.
  - `site/data/skill_lift.json` — a separate file with per-model lift,
    consumed by the second table on the static site.

Run after any new eval result lands under `results/`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from frugalmind.leaderboard import (  # noqa: E402
    build_leaderboard,
    build_skill_lift_leaderboard,
    load_eval_results,
)


def _explode_skill_lift_rows(payload: dict, source_file: str) -> list[dict]:
    """Turn one skill-lift payload into two-rows-per-model leaderboard rows."""
    out: list[dict] = []
    for row in payload.get("rows", []):
        base = {
            "model_id": row["model_id"],
            "suite": row["suite"],
            "skill_name": row["skill_name"],
            "skill_version": row["skill_version"],
            "n_completed": row["n_total"],
            "n_total": row["n_total"],
            "run_file": source_file,
        }
        out.append({
            **base,
            "agent_condition": "generic-coding-agent",
            "score": row["score_none"],
            "cost_usd": row["cost_none_usd"],
        })
        out.append({
            **base,
            "agent_condition": f"{row['skill_name']}+skill-{row['skill_version']}",
            "score": row["score_full"],
            "cost_usd": row["cost_full_usd"],
        })
    return out


def main() -> int:
    results_dir = REPO / "results"
    site_data = REPO / "site" / "data"
    site_data.mkdir(parents=True, exist_ok=True)

    # --- Regular leaderboard rows from per-eval JSON files -----------------
    regular_results = load_eval_results(results_dir)
    # Filter out the skill-lift payloads so we don't double-count them.
    skill_lift_payloads = []
    cleaned: list[dict] = []
    for r in regular_results:
        # `load_eval_results` flattens skill-lift `rows` into items; identify
        # them by the presence of `score_none` / `score_full`.
        if "score_none" in r or "score_full" in r:
            skill_lift_payloads.append(r)
            continue
        cleaned.append(r)

    # Skill-lift demo file is read separately for the second table.
    demo_path = results_dir / "demo_small_models.json"
    demo_payload = json.loads(demo_path.read_text()) if demo_path.exists() else {"rows": []}
    cleaned.extend(_explode_skill_lift_rows(demo_payload, demo_path.name))

    leaderboard = build_leaderboard(cleaned, source="results/*.json + demo_small_models.json")
    (site_data / "leaderboard.json").write_text(json.dumps(leaderboard, indent=2) + "\n")
    print(f"Wrote {site_data / 'leaderboard.json'} with {len(leaderboard['leaderboard'])} rows")

    # --- Skill-lift table for the second site section ---------------------
    if demo_payload.get("rows"):
        # Re-encode the demo payload as a skill-lift leaderboard so the site
        # has a single canonical schema.
        from frugalmind.leaderboard import SkillLiftRow

        rows = [
            SkillLiftRow(
                model_id=r["model_id"],
                suite=r["suite"],
                skill_name=r["skill_name"],
                skill_version=r["skill_version"],
                score_none=r["score_none"],
                score_full=r["score_full"],
                lift=r["lift"],
                cost_none_usd=r["cost_none_usd"],
                cost_full_usd=r["cost_full_usd"],
                cost_lift_pct=r.get("cost_lift_pct"),
                n_total=r["n_total"],
            )
            for r in demo_payload["rows"]
        ]
        skill_payload = build_skill_lift_leaderboard(rows, source="results/demo_small_models.json")
        (site_data / "skill_lift.json").write_text(json.dumps(skill_payload, indent=2) + "\n")
        print(f"Wrote {site_data / 'skill_lift.json'} with {len(skill_payload['rows'])} rows")
    else:
        print("No skill-lift rows found; skipping skill_lift.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
