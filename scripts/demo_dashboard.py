"""Populate the dashboard with a two-eval, three-model, skill-conditioned demo.

Evals
-----
- ``synthetic_stalta`` (STA/LTA detection on Ridgecrest-derived synthetic cases)
- ``dvv_processing``   (codameter dv/v param-recommendation; the manifest is
  regenerated to a writable cache because the pinned codameter ships its golden
  data with a source-checkout path — a codameter packaging fix is the real cure)

Honesty note
------------
There is no live model backend in this environment, so model *responses* are
simulated per (model, skill, item) with a deterministic hash — but every score
is a genuine output of the real deterministic scorer (pick_f1 for detection,
codameter dv/v recovery for the param task). Costs are illustrative. The point
is to exercise the real pipeline end-to-end and show what the dashboard renders.

Run:  pixi run -e full python scripts/demo_dashboard.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from frugalmind.leaderboard import (  # noqa: E402
    SkillLiftRow,
    build_leaderboard,
    build_skill_lift_leaderboard,
)
from frugalmind_suites.synthetic_stalta.items import SyntheticSTALTASuite  # noqa: E402
from frugalmind_suites.synthetic_stalta.scorers import (  # noqa: E402
    make_scorer_from_spec as stalta_scorer_from_spec,
)

# --- 3 models: competence + how much a skill lifts them + illustrative cost --
MODELS = [
    {"id": "qwen2.5:7b", "openness": "open-source-open-weight",
     "base": 0.40, "skill_gain": 0.42, "cost": 0.00020},
    {"id": "llama3.1:8b", "openness": "open-source-open-weight",
     "base": 0.62, "skill_gain": 0.26, "cost": 0.00030},
    {"id": "claude-haiku-4-5-20251001", "openness": "closed-source-api",
     "base": 0.86, "skill_gain": 0.10, "cost": 0.00220},
]
SKILL = {
    "synthetic_stalta": ("stalta-detection", "v0.1-demo"),
    "dvv_processing": ("dvv-processing", "v0.1-demo"),
}


def _u(*parts: str) -> float:
    """Deterministic pseudo-random in [0,1) from a label (no Math.random)."""
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(h[:12], 16) / 16**12


def _competence(m: dict, mode: str) -> float:
    return min(0.99, m["base"] + (m["skill_gain"] if mode == "full" else 0.0))


# --------------------------------------------------------------------------- #
# Item providers: (item_id, gold, scorer, good_response, degraded_response)
# --------------------------------------------------------------------------- #
def _stalta_items():
    suite = SyntheticSTALTASuite(split="validation")
    for c in suite._cases():
        _, gold, spec, meta = suite._compose(c)
        scorer = stalta_scorer_from_spec(spec)
        good = json.dumps(gold)
        if gold:  # positive: degraded = miss the (first) event
            degraded = json.dumps(gold[1:]) if len(gold) > 1 else "[]"
        else:  # negative: degraded = a false alarm
            degraded = "[30.0]"
        yield (meta["case_id"], gold, scorer, good, degraded)


def _dvv_items():
    # Regenerate codameter's golden manifest into a writable cache first.
    from codameter import frugalmind as cfm
    from codameter import golden

    cache = REPO / "results" / "codameter_golden"
    cache.mkdir(parents=True, exist_ok=True)
    golden.DATA_DIR = cache
    golden.MANIFEST = cache / "manifest.json"
    if not golden.MANIFEST.exists():
        golden.regenerate_manifest()

    rows = cfm.build_rows("param_recommendation", split="validation")
    bad_config = json.dumps({"freqmin": 9.5, "freqmax": 10.0})
    for r in rows:
        scorer = cfm.make_scorer_from_spec(r["scorer_spec"])
        good = json.dumps(r["metadata"]["recommended_config"])
        yield (r["id"], r["gold"], scorer, good, bad_config)


SUITES = {"synthetic_stalta": _stalta_items, "dvv_processing": _dvv_items}


def _run_arm(model: dict, suite_name: str, items, mode: str) -> dict:
    # A model of competence p answers correctly the p-fraction of *easiest*
    # items. Difficulty order is per-item (same for every model), so a stronger
    # model's correct set is a superset of a weaker one's — monotonic ranks, no
    # small-sample inversions. A skill raises p, extending the frontier.
    p = _competence(model, mode)
    ranked = sorted(items, key=lambda it: _u(suite_name, it[0]))
    n = len(ranked)
    k = round(p * n)
    score_sum = 0.0
    for idx, (_id, gold, scorer, good, degraded) in enumerate(ranked):
        resp = good if idx < k else degraded
        score_sum += float(scorer(resp, gold))
    # Illustrative cost: a small per-item price, with a modest premium for the
    # longer skill-loaded prompt in `full`.
    cost = n * model["cost"] * (1.15 if mode == "full" else 1.0)
    return {"score": score_sum / n if n else 0.0, "cost": cost, "n": n}


def main() -> int:
    skill_rows: list[SkillLiftRow] = []
    flat: list[dict] = []
    for suite_name, provider in SUITES.items():
        skill_name, skill_version = SKILL[suite_name]
        for m in MODELS:
            none = _run_arm(m, suite_name, list(provider()), "none")
            full = _run_arm(m, suite_name, list(provider()), "full")
            cost_lift = (
                (full["cost"] - none["cost"]) / none["cost"] * 100.0
                if none["cost"] > 0 else None
            )
            skill_rows.append(SkillLiftRow(
                model_id=m["id"], suite=suite_name,
                skill_name=skill_name, skill_version=skill_version,
                score_none=none["score"], score_full=full["score"],
                lift=full["score"] - none["score"],
                cost_none_usd=none["cost"], cost_full_usd=full["cost"],
                cost_lift_pct=cost_lift, n_total=none["n"],
                openness=m["openness"], toolset="custom-interface",
            ))
            for mode, arm in (("none", none), ("full", full)):
                cond = ("generic-coding-agent" if mode == "none"
                        else f"{skill_name}+skill-{skill_version}")
                flat.append({
                    "model_id": m["id"], "suite": suite_name,
                    "agent_condition": cond, "score": arm["score"],
                    "cost_usd": arm["cost"], "n_completed": arm["n"],
                    "n_total": arm["n"], "openness": m["openness"],
                    "toolset": "standard" if mode == "none" else "custom-interface",
                    "skill_name": skill_name, "skill_version": skill_version,
                    "run_file": "demo_dashboard.py",
                })

    note = ("Demonstration: simulated model responses scored by the real "
            "deterministic scorers (no live model backend in this environment); "
            "costs are illustrative.")
    site = REPO / "site" / "data"
    site.mkdir(parents=True, exist_ok=True)

    lb = build_leaderboard(flat, source="scripts/demo_dashboard.py (2 evals x 3 models)")
    lb["notes"].insert(0, note)
    (site / "leaderboard.json").write_text(json.dumps(lb, indent=2) + "\n")

    sl = build_skill_lift_leaderboard(skill_rows, source="scripts/demo_dashboard.py")
    sl["notes"].insert(0, note)
    (site / "skill_lift.json").write_text(json.dumps(sl, indent=2) + "\n")

    print(f"leaderboard rows: {len(lb['leaderboard'])}  skill-lift rows: {len(sl['rows'])}")
    for r in sl["rows"]:
        print(f"  {r['suite']:16} {r['model_id']:26} "
              f"none={r['score_none']:.2f} full={r['score_full']:.2f} "
              f"lift={r['lift']:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
