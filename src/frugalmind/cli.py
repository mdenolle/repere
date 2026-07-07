"""Command-line helpers for local FrugalMind development.

The CLI exposes deterministic subcommands that don't require model providers
(``smoke-eval``, ``export-leaderboard``, ``list-models``, ``list-skills``) and
provider-touching subcommands that do (``run-ollama-intent``,
``run-skill-lift``).
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from frugalmind_suites.sta_lta import STALTAIntentExtractionSuite

from . import EvalRunner, Generation, ModelCard, ModelRegistry
from .export import export_suites
from .leaderboard import (
    LeaderboardRunner,
    export_leaderboard,
    export_skill_lift_leaderboard,
)
from .registry import load_registry_yaml
from .skills import SkillLoader, SkillManifest, render_with_skill

ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / ".github" / "skills"
SKILL_MANIFEST = SKILLS_DIR / "manifest.yaml"
DEFAULT_MODELS_YAML = ROOT / "config" / "models.yaml"
LEGACY_SEISMO_SKILL_PATH = SKILLS_DIR / "seismo-data-agent" / "SKILL.md"


def _slugify(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")


def _read_skill_prompt(path: Path = LEGACY_SEISMO_SKILL_PATH) -> str:
    """Strip frontmatter from a SKILL.md and return the body (legacy helper)."""
    if not path.exists():
        return ""
    text = path.read_text()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            text = parts[2]
    return text.strip()


def _ollama_generate(
    *,
    model: str,
    prompt: str,
    host: str = "http://127.0.0.1:11434",
    timeout_s: float = 180.0,
) -> tuple[str, float]:
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0, "num_ctx": 4096},
        }
    ).encode()
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            data = json.loads(response.read().decode())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama request failed for {model!r}: {exc}") from exc
    latency_s = time.perf_counter() - start
    return str(data.get("response", "")), latency_s


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
    payload = {**result.__dict__, "suite": "sta_lta.intent_extraction"}
    path.write_text(json.dumps(payload, indent=2))
    return path


def _resolve_skill_for_intent(
    skill_name: str | None, condition: str | None
) -> tuple[str | None, str]:
    """Return (skill_name, agent_condition) following both new and legacy flags."""
    # Back-compat: --condition seismo-skill maps to legacy seismo-data-agent.
    if skill_name is None:
        if condition == "seismo-skill":
            return "seismo-data-agent", "SeismoDataAgent+skill-v0.1-draft"
        return None, "generic-coding-agent"
    if skill_name == "seismo-data-agent":
        return skill_name, "SeismoDataAgent+skill-v0.1-draft"
    return skill_name, f"{skill_name}+skill"


def _run_ollama_intent_eval(
    *,
    model: str,
    results_dir: Path,
    skill_name: str | None,
    skill_mode: str,
    condition: str | None,
    host: str,
    timeout_s: float,
) -> Path:
    """Run a real local Ollama model on the public STA/LTA intent suite."""
    suite = STALTAIntentExtractionSuite()
    items = list(suite.items())

    resolved_skill_name, agent_condition = _resolve_skill_for_intent(skill_name, condition)
    skill_obj = None
    if resolved_skill_name and resolved_skill_name != "seismo-data-agent":
        skill_obj = SkillLoader(skills_dir=SKILLS_DIR).get(resolved_skill_name)
    elif resolved_skill_name == "seismo-data-agent":
        # Legacy path: use the body-only injection that older results used.
        legacy_prompt = _read_skill_prompt()
        if legacy_prompt:

            class _LegacySkillStub:
                def render(self, _mode: str) -> str:
                    return legacy_prompt

            skill_obj = _LegacySkillStub()  # type: ignore[assignment]

    scores: list[float] = []
    details: list[dict[str, Any]] = []
    total_latency = 0.0

    for index, (prompt, gold, scorer) in enumerate(items):
        if skill_obj is None or skill_mode == "none":
            full_prompt = prompt
        else:
            full_prompt = render_with_skill(prompt, skill_obj, mode=skill_mode)  # type: ignore[arg-type]
        text, latency_s = _ollama_generate(
            model=model,
            prompt=full_prompt,
            host=host,
            timeout_s=timeout_s,
        )
        item_score = float(scorer(text, gold))
        scores.append(item_score)
        total_latency += latency_s
        details.append(
            {
                "item_index": index,
                "score": item_score,
                "latency_s": latency_s,
                "output_preview": text[:500],
            }
        )

    skill_version = getattr(
        skill_obj, "version", "v0.1-draft" if resolved_skill_name == "seismo-data-agent" else None
    )

    result = {
        "model_id": model,
        "agent_condition": agent_condition,
        "skill_name": resolved_skill_name,
        "skill_version": skill_version,
        "skill_mode": skill_mode if resolved_skill_name else None,
        "suite": "sta_lta.intent_extraction",
        "score": sum(scores) / len(items) if items else 0.0,
        "cost_usd": 0.0,
        "n_completed": len(scores),
        "n_total": len(items),
        "latency_s": total_latency,
        "details": details,
    }

    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"ollama_{_slugify(model)}_{_slugify(agent_condition)}.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    return path


def _list_models(args: argparse.Namespace) -> int:
    registry = load_registry_yaml(args.registry)
    rows = []
    for c in registry.list():
        rows.append(
            {
                "id": c.id,
                "family": c.family,
                "tier": c.metadata.get("tier"),
                "backend": c.backend,
                "size_b": c.size_b,
                "cost_per_1k_in": c.cost_per_1k_in,
                "cost_per_1k_out": c.cost_per_1k_out,
            }
        )
    print(json.dumps(rows, indent=2))
    return 0


def _list_skills(_: argparse.Namespace) -> int:
    if not SKILL_MANIFEST.exists():
        print(json.dumps({"skills": [], "manifest": str(SKILL_MANIFEST)}))
        return 0
    manifest = SkillManifest.from_yaml(SKILL_MANIFEST)
    skills = SkillLoader(skills_dir=SKILLS_DIR).load_all()
    out = []
    for name in manifest.names() + [n for n in skills if n not in manifest.names()]:
        skill = skills.get(name)
        out.append(
            {
                "name": name,
                "version": getattr(skill, "version", None),
                "task_kind": getattr(skill, "task_kind", None),
                "suites": manifest.suites_for_skill(name),
            }
        )
    print(json.dumps(out, indent=2))
    return 0


def _run_skill_lift(args: argparse.Namespace) -> int:
    """Run the skill-lift benchmark over an offline echo registry (smoke).

    This subcommand is provider-free: it uses a deterministic
    `EchoAdapter`-style stub so CI can exercise the runner shape without keys.
    For real provider runs, plug `frugalmind.adapters.adapter_from_env` into
    your own script.
    """
    from .adapters import EchoAdapter

    suite = STALTAIntentExtractionSuite()
    suite_id = "sta_lta.intent_extraction"
    skill_name = args.skill or "stalta-detection"
    skill = SkillLoader(skills_dir=SKILLS_DIR).get(skill_name)

    registry = ModelRegistry()
    registry.register(
        ModelCard(
            id="stub-local",
            family="stub",
            size_b=0,
            context_window=32_000,
            backend="local",
            cost_per_1k_in=0.0,
            cost_per_1k_out=0.0,
        )
    )

    def factory(card: ModelCard) -> EchoAdapter:
        return EchoAdapter(_card=card, response_text="{}")

    def render(prompt: str, mode: str) -> str:
        return render_with_skill(prompt, skill, mode=mode)  # type: ignore[arg-type]

    runner = LeaderboardRunner(
        suite=suite,
        suite_id=suite_id,
        skill_name=skill_name,
        skill_version=skill.version,
        adapter_factory=factory,
        prompt_render=render,
    )
    rows = runner.run(registry.list())
    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    export_skill_lift_leaderboard(rows, out)
    print(f"Wrote {out}")
    return 0


def _all_registered_suites() -> list[Any]:
    """Return one instance of every benchmark suite known to the package.

    Add new suite families to this function as they are introduced; the
    ``export-suite`` CLI walks the returned list when ``--suite`` is omitted.

    The dv/v suites need their scoring backend (``codameter``) to export rows, so
    they are included only when it is importable. This keeps a bulk export
    working for contributors who have not installed the ``[dvv]`` extra.
    """
    from importlib.util import find_spec

    from frugalmind_suites.sta_lta import ALL_SUITES as STA_LTA_SUITES

    suites = list(STA_LTA_SUITES)
    if find_spec("codameter") is not None:
        from frugalmind_suites.dvv import ALL_SUITES as DVV_SUITES

        suites.extend(DVV_SUITES)
    return suites


def _resolve_suites(suite_ids: list[str] | None) -> list[Any]:
    """Pick one or more registered suites by their ``<dataset_id>.<suite_id>`` key."""
    all_suites = _all_registered_suites()
    if not suite_ids:
        return all_suites
    by_key = {f"{s.dataset_id}.{s.suite_id}": s for s in all_suites}
    selected: list[Any] = []
    for sid in suite_ids:
        if sid not in by_key:
            available = ", ".join(sorted(by_key)) or "(none)"
            raise SystemExit(f"Unknown suite {sid!r}. Available: {available}")
        selected.append(by_key[sid])
    return selected


def _run_export_suite(args: argparse.Namespace) -> int:
    suites = _resolve_suites(args.suite)

    if args.visibility != "all":
        for s in suites:
            # All current STA/LTA suites accept visibility= via _SplitAwareSuite.
            s.visibility = args.visibility  # type: ignore[attr-defined]

    manifest = export_suites(suites, out_dir=args.out, version=args.version)
    print(json.dumps(manifest, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FrugalMind local eval helpers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    smoke = subparsers.add_parser("smoke-eval", help="Run a deterministic stub eval")
    smoke.add_argument("--results-dir", default=Path("results"), type=Path)

    leaderboard = subparsers.add_parser(
        "export-leaderboard", help="Export static leaderboard JSON from eval results"
    )
    leaderboard.add_argument("--results-dir", default=Path("results"), type=Path)
    leaderboard.add_argument("--output", default=Path("site/data/leaderboard.json"), type=Path)

    ollama = subparsers.add_parser(
        "run-ollama-intent",
        help="Run a local Ollama model on the public STA/LTA intent suite",
    )
    ollama.add_argument("--model", required=True)
    ollama.add_argument("--results-dir", default=Path("results"), type=Path)
    ollama.add_argument(
        "--skill",
        default=None,
        help="Name of a skill from .github/skills/ (e.g. stalta-detection). "
        "Mutually exclusive with --condition.",
    )
    ollama.add_argument(
        "--skill-mode",
        choices=["none", "instructions", "full"],
        default="instructions",
        help="Skill injection mode (default: instructions)",
    )
    ollama.add_argument(
        "--condition",
        choices=["generic", "seismo-skill"],
        default=None,
        help="Legacy: 'seismo-skill' maps to seismo-data-agent. Prefer --skill.",
    )
    ollama.add_argument("--host", default="http://127.0.0.1:11434")
    ollama.add_argument("--timeout-s", default=180.0, type=float)

    list_models = subparsers.add_parser(
        "list-models",
        help="List registered model cards from a models.yaml file",
    )
    list_models.add_argument("--registry", default=DEFAULT_MODELS_YAML, type=Path)

    list_skills_p = subparsers.add_parser(
        "list-skills",
        help="List skills declared in .github/skills/ and their suite bindings",
    )
    list_skills_p.set_defaults(_handler=_list_skills)

    skill_lift = subparsers.add_parser(
        "run-skill-lift",
        help="Run a deterministic skill-lift benchmark using stub adapters",
    )
    skill_lift.add_argument("--skill", default="stalta-detection")
    skill_lift.add_argument("--output", default=Path("results/skill_lift.json"), type=Path)

    export_suite_p = subparsers.add_parser(
        "export-suite",
        help="Export curated (prompt, gold) JSONL artifacts for one or more suites",
    )
    export_suite_p.add_argument(
        "--suite",
        action="append",
        default=None,
        help="Fully-qualified suite id, e.g. 'sta_lta.intent_extraction'. "
        "Repeat to export multiple. Omit to export every registered suite.",
    )
    export_suite_p.add_argument(
        "--out",
        default=Path("datasets"),
        type=Path,
        help="Root output directory; files land under <out>/<dataset_id>/<version>/",
    )
    export_suite_p.add_argument(
        "--version",
        default=None,
        help="Override version tag (default: each suite's own .version attribute).",
    )
    export_suite_p.add_argument(
        "--visibility",
        choices=["public", "private", "all"],
        default="all",
        help="Filter rows by visibility (default: all).",
    )

    args = parser.parse_args(argv)
    if args.command == "smoke-eval":
        path = _run_stub_eval(args.results_dir)
        print(f"Wrote {path}")
        return 0
    if args.command == "export-leaderboard":
        path = export_leaderboard(args.results_dir, args.output)
        print(f"Wrote {path}")
        return 0
    if args.command == "run-ollama-intent":
        path = _run_ollama_intent_eval(
            model=args.model,
            results_dir=args.results_dir,
            skill_name=args.skill,
            skill_mode=args.skill_mode,
            condition=args.condition,
            host=args.host,
            timeout_s=args.timeout_s,
        )
        print(f"Wrote {path}")
        return 0
    if args.command == "list-models":
        return _list_models(args)
    if args.command == "list-skills":
        return _list_skills(args)
    if args.command == "run-skill-lift":
        return _run_skill_lift(args)
    if args.command == "export-suite":
        return _run_export_suite(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
