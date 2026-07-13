"""Populate the dashboard with a two-eval, three-model, skill-conditioned demo.

Evals
-----
- ``synthetic_stalta`` (STA/LTA detection on Ridgecrest-derived synthetic cases)
- ``dvv_processing``   (codameter dv/v param-recommendation; the pinned
  codameter includes the installed-golden-dir fix, so its golden data resolves
  or regenerates on an installed copy with no workaround here)

Two modes
---------
``--live``   Real inference. Each item's real prompt is rendered with the bound
             skill (``none`` vs ``full``), sent to a real backend via
             ``adapter_from_env`` (Ollama for the local 7-8B models, the
             Anthropic API for the cloud row), and the model's actual text is
             graded by the real scorer. Costs come from real token usage.

(default)    Simulated responses. Model *responses* are synthesised per
             (model, skill, item) with a deterministic hash, so the script runs
             in CI with no GPU, no Ollama daemon and no API keys. Every score is
             still a genuine output of the real scorer, but the board is a
             harness demonstration, NOT a capability measurement.

In both modes the suites, truth sets, scorers, skill injection, sandbox and cost
model are the same real code paths. Only the source of the model text differs.

Run (simulated):  pixi run -e full python scripts/demo_dashboard.py
Run (real):       ollama serve &
                  ollama pull qwen2.5:7b llama3.1:8b olmo2:7b
                  export ANTHROPIC_API_KEY=...        # optional cloud row
                  pixi run -e full python scripts/demo_dashboard.py --live
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from frugalmind import load_env_keys  # noqa: E402
from frugalmind.adapters import adapter_from_env  # noqa: E402
from frugalmind.leaderboard import (  # noqa: E402
    SkillLiftRow,
    build_leaderboard,
    build_skill_lift_leaderboard,
)
from frugalmind.registry import load_registry_yaml  # noqa: E402
from frugalmind.skills import SkillLoader, render_with_skill  # noqa: E402
from frugalmind_suites.synthetic_stalta.items import SyntheticSTALTASuite  # noqa: E402
from frugalmind_suites.synthetic_stalta.scorers import (  # noqa: E402
    make_scorer_from_spec as stalta_scorer_from_spec,
)

# --- 3 models: competence + how much a skill lifts them + illustrative cost --
# Four laptop-scale open-weight models (Ollama, 7-8B) plus one cloud API model
# as the reference ceiling. Small models start lower and gain *more* from a
# domain skill -- that inverse relationship is the frugality thesis, and it is
# only visible when the board contains models that don't automatically clear the
# quality floor. See docs/laptop_scale_mvp.md.
MODELS = [
    {"id": "olmo2:7b", "openness": "open-source-open-weight",
     "base": 0.34, "skill_gain": 0.44, "cost": 0.00018},
    {"id": "qwen2.5:7b", "openness": "open-source-open-weight",
     "base": 0.40, "skill_gain": 0.42, "cost": 0.00020},
    {"id": "deepseek-r1:7b", "openness": "open-source-open-weight",
     "base": 0.55, "skill_gain": 0.31, "cost": 0.00025},
    {"id": "llama3.1:8b", "openness": "open-source-open-weight",
     "base": 0.62, "skill_gain": 0.26, "cost": 0.00030},
    {"id": "claude-haiku-4-5-20251001", "openness": "closed-source-api",
     "base": 0.86, "skill_gain": 0.10, "cost": 0.00220},
]
SKILL = {
    "synthetic_stalta": ("stalta-detection", "v0.1-demo"),
    "dvv_processing": ("dvv-processing", "v0.1-demo"),
}

# EvalHub categories. The leaderboard filters on these; keep in sync with the
# category cards on the site.
#   document          — literature / RAG / translation / multimodal
#   software-agent    — agents driving real scientific software (detectors,
#                       noisepy, specfem, seisbench, codameter)
#   research-workflow — orchestrators, scored on their call trajectory
SUITE_CATEGORY = {
    "synthetic_stalta": "software-agent",
    "dvv_processing": "software-agent",
    "lit_rag": "document",
    "orchestration": "research-workflow",
}


def _u(*parts: str) -> float:
    """Deterministic pseudo-random in [0,1) from a label (no Math.random)."""
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(h[:12], 16) / 16**12


def _competence(m: dict, mode: str) -> float:
    return min(0.99, m["base"] + (m["skill_gain"] if mode == "full" else 0.0))


# --------------------------------------------------------------------------- #
# Item providers: (item_id, prompt, gold, scorer, good_response, degraded)
#
# `prompt` is the real suite prompt (used by --live). `good`/`degraded` are the
# canned responses the simulator picks between; --live ignores them.
# --------------------------------------------------------------------------- #
def _stalta_items():
    suite = SyntheticSTALTASuite(split="validation")
    for c in suite._cases():
        prompt, gold, spec, meta = suite._compose(c)
        scorer = stalta_scorer_from_spec(spec)
        # The task is now code-generation, so the simulator's canned answers are
        # code too: a snippet that records the right onsets vs one that doesn't.
        good = f"```python\nrecord(picks={json.dumps(gold)})\n```"
        if gold:  # positive: degraded = miss the (first) event
            missed = gold[1:] if len(gold) > 1 else []
            degraded = f"```python\nrecord(picks={json.dumps(missed)})\n```"
        else:  # negative: degraded = a false alarm
            degraded = "```python\nrecord(picks=[30.0])\n```"
        yield (meta["case_id"], prompt, gold, scorer, good, degraded)


def _dvv_items():
    # codameter#15 makes an installed copy resolve/regenerate its golden data
    # (per-user cache), so no manifest workaround is needed here.
    from codameter import frugalmind as cfm

    rows = cfm.build_rows("param_recommendation", split="validation")
    bad_config = json.dumps({"freqmin": 9.5, "freqmax": 10.0})
    for r in rows:
        scorer = cfm.make_scorer_from_spec(r["scorer_spec"])
        good = json.dumps(r["metadata"]["recommended_config"])
        yield (r["id"], r["prompt"], r["gold"], scorer, good, bad_config)


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
    for idx, (_id, _prompt, gold, scorer, good, degraded) in enumerate(ranked):
        resp = good if idx < k else degraded
        score_sum += float(scorer(resp, gold))
    # Illustrative cost: a small per-item price, with a modest premium for the
    # longer skill-loaded prompt in `full`.
    cost = n * model["cost"] * (1.15 if mode == "full" else 1.0)
    return {"score": score_sum / n if n else 0.0, "cost": cost, "n": n}


def _run_arm_live(adapter, skill, suite_name: str, items, mode: str) -> dict:
    """Real inference: render the prompt with the skill, call the model, score
    its actual text with the real scorer, and bill real token usage.

    A single item that errors (timeout, refusal, malformed backend reply) scores
    0 rather than killing the run — a model that cannot answer *is* a result.
    """
    n = len(items)
    score_sum = 0.0
    cost = 0.0
    errors = 0
    t0 = time.time()
    for i, (item_id, prompt, gold, scorer, _good, _degraded) in enumerate(items, 1):
        rendered = render_with_skill(prompt, skill, "full" if mode == "full" else "none")
        try:
            gen = adapter.generate(rendered)
            text = gen.text
            cost += float(getattr(gen, "cost_usd", 0.0) or 0.0)
        except Exception as exc:  # noqa: BLE001 - a failed call is a real datum
            errors += 1
            text = ""
            print(f"      ! {item_id}: {type(exc).__name__}: {exc}", flush=True)
        try:
            score_sum += float(scorer(text, gold))
        except Exception:  # a scorer that chokes on garbage output scores 0
            pass
        if i % 5 == 0 or i == n:
            print(f"      {suite_name}/{mode}: {i}/{n} "
                  f"({time.time() - t0:.0f}s)", flush=True)
    return {
        "score": score_sum / n if n else 0.0,
        "cost": cost,
        "n": n,
        "errors": errors,
    }


def _live_setup(model_ids: list[str]):
    """Build (card, adapter) for each requested model, skipping any that cannot
    be reached — a missing Ollama pull or absent API key should degrade the board,
    not abort the run."""
    load_env_keys(REPO / ".env")  # optional: ANTHROPIC_API_KEY etc.
    registry = load_registry_yaml(REPO / "config" / "models.yaml")
    live = []
    for mid in model_ids:
        try:
            card = registry.get(mid)
        except KeyError:
            print(f"  ! {mid}: not in config/models.yaml — skipping")
            continue
        try:
            adapter = adapter_from_env(card)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {mid}: no adapter ({exc}) — skipping")
            continue
        live.append((card, adapter))
    return live


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true",
                    help="real inference via Ollama / Anthropic instead of simulation")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap items per suite (useful for a quick live smoke run)")
    ap.add_argument("--models", nargs="*", default=None,
                    help="model ids to run (default: the MODELS list)")
    ap.add_argument("--merge", action="store_true",
                    help="keep rows from a previous run for models not in this one "
                         "(e.g. add a cloud row without re-running the local sweep)")
    args = ap.parse_args()

    if args.live:
        return _main_live(args)

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
    return _emit(flat, skill_rows, note, "scripts/demo_dashboard.py (simulated)")


def _merge_previous(flat, skill_rows):
    """Fold in rows from a previous run for models NOT in this run.

    Lets an expensive local sweep and a fast cloud row be produced in separate
    passes without re-running the slow one. Rows for a model present in *this*
    run always replace its earlier rows.
    """
    site = REPO / "site" / "data"
    new_models = {r["model_id"] for r in flat}

    lb_path = site / "leaderboard.json"
    if lb_path.exists():
        prev = json.loads(lb_path.read_text()).get("leaderboard", [])
        for r in prev:
            if r.get("model_id") in new_models:
                continue
            r = dict(r)
            # rank/efficiency are derived; build_leaderboard recomputes them.
            r.pop("rank", None)
            r.pop("efficiency_score", None)
            flat.append(r)

    sl_path = site / "skill_lift.json"
    if sl_path.exists():
        prev = json.loads(sl_path.read_text()).get("rows", [])
        fields = set(SkillLiftRow.__dataclass_fields__)
        for r in prev:
            if r.get("model_id") in new_models:
                continue
            skill_rows.append(SkillLiftRow(**{k: v for k, v in r.items() if k in fields}))
    return flat, skill_rows


def _emit(flat, skill_rows, note: str, source: str, merge: bool = False) -> int:
    site = REPO / "site" / "data"
    site.mkdir(parents=True, exist_ok=True)
    if merge:
        flat, skill_rows = _merge_previous(flat, skill_rows)

    lb = build_leaderboard(flat, source=source)
    lb["notes"].insert(0, note)
    for r in lb["leaderboard"]:
        r["category"] = SUITE_CATEGORY.get(r.get("suite"), "software-agent")
    (site / "leaderboard.json").write_text(json.dumps(lb, indent=2) + "\n")

    sl = build_skill_lift_leaderboard(skill_rows, source=source)
    sl["notes"].insert(0, note)
    for r in sl["rows"]:
        r["category"] = SUITE_CATEGORY.get(r.get("suite"), "software-agent")
    (site / "skill_lift.json").write_text(json.dumps(sl, indent=2) + "\n")

    print(f"\nleaderboard rows: {len(lb['leaderboard'])}  skill-lift rows: {len(sl['rows'])}")
    for r in sl["rows"]:
        print(f"  {r['suite']:16} {r['model_id']:26} "
              f"none={r['score_none']:.2f} full={r['score_full']:.2f} "
              f"lift={r['lift']:+.2f}  cost=${r['cost_full_usd']:.4f}")
    return 0


def _main_live(args) -> int:
    """Real inference against Ollama (local) and/or the Anthropic API (cloud)."""
    model_ids = args.models or [m["id"] for m in MODELS]
    openness = {m["id"]: m["openness"] for m in MODELS}
    loader = SkillLoader(skills_dir=REPO / ".github" / "skills")

    live = _live_setup(model_ids)
    if not live:
        print("no reachable models; is `ollama serve` running / ANTHROPIC_API_KEY set?")
        return 1
    print(f"live backends: {', '.join(c.id for c, _ in live)}\n")

    skill_rows: list[SkillLiftRow] = []
    flat: list[dict] = []
    for suite_name, provider in SUITES.items():
        skill_name, _ = SKILL[suite_name]
        skill = loader.get(skill_name)
        # Report the version the SKILL.md actually declares, not a placeholder:
        # a live row must be traceable to the exact guidance that produced it.
        skill_version = skill.version
        items = list(provider())
        if args.limit:
            items = items[: args.limit]
        for card, adapter in live:
            print(f"  {card.id} on {suite_name} ({len(items)} items x 2 arms)")
            none = _run_arm_live(adapter, skill, suite_name, items, "none")
            full = _run_arm_live(adapter, skill, suite_name, items, "full")
            cost_lift = (
                (full["cost"] - none["cost"]) / none["cost"] * 100.0
                if none["cost"] > 0 else None
            )
            op = openness.get(card.id, "unknown")
            skill_rows.append(SkillLiftRow(
                model_id=card.id, suite=suite_name,
                skill_name=skill_name, skill_version=skill_version,
                score_none=none["score"], score_full=full["score"],
                lift=full["score"] - none["score"],
                cost_none_usd=none["cost"], cost_full_usd=full["cost"],
                cost_lift_pct=cost_lift, n_total=none["n"],
                openness=op, toolset="custom-interface",
            ))
            for mode, arm in (("none", none), ("full", full)):
                cond = ("generic-coding-agent" if mode == "none"
                        else f"{skill_name}+skill-{skill_version}")
                flat.append({
                    "model_id": card.id, "suite": suite_name,
                    "agent_condition": cond, "score": arm["score"],
                    "cost_usd": arm["cost"],
                    "n_completed": arm["n"] - arm["errors"], "n_total": arm["n"],
                    "openness": op,
                    "toolset": "standard" if mode == "none" else "custom-interface",
                    "skill_name": skill_name, "skill_version": skill_version,
                    "run_file": "demo_dashboard.py --live",
                })

    note = ("LIVE RUN: real model inference (Ollama locally / Anthropic API), real "
            "prompts, real skill injection, graded by the real deterministic scorers. "
            "Costs are actual token usage; local open-weight models bill $0 marginal.")
    return _emit(flat, skill_rows, note, "scripts/demo_dashboard.py --live",
                 merge=args.merge)


if __name__ == "__main__":
    raise SystemExit(main())
