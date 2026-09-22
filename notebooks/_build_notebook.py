"""Generator for the Repère quickstart notebook.

Run once to (re)generate `01_skill_lift_quickstart.ipynb`.
This script is checked in so the notebook is reproducible.
"""

from __future__ import annotations

import json
from pathlib import Path


def md(text: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": text.splitlines(keepends=True),
    }


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.splitlines(keepends=True),
    }


CELLS = [
    md(
        """\
# Repère quickstart — three small models, skill-lift benchmark

This notebook walks through the smallest end-to-end run the framework supports:

1. Load three **small-tier** models from `config/models.yaml`.
2. Load the `stalta-detection` **skill**.
3. Run the public **STA/LTA intent-extraction** suite under two conditions:
   - `none` — passthrough prompt (baseline)
   - `full` — skill body + references injected before the prompt
4. Compute **skill lift** (= `score_full - score_none`) for each model.
5. Export a leaderboard JSON.

Everything in the **default path runs offline** with a deterministic
`EchoAdapter` that simulates each of the three models. A second section at the
end shows how to swap in a **live Ollama** server with one line.

> Prerequisites: `pip install -e ".[dev]"` from the repo root, plus `pip install jupyter` if you don't already have it.
"""
    ),
    md("## 1. Imports and paths"),
    code(
        """\
from __future__ import annotations
import json, sys
from pathlib import Path

# This notebook lives at <repo>/notebooks/. Add <repo>/src to sys.path so the
# package is importable without a pip install.
REPO = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(REPO / "src"))

from repere import ModelCard
from repere.adapters import EchoAdapter, OpenAICompatAdapter
from repere.budget import BudgetGuard
from repere.leaderboard import LeaderboardRunner, build_skill_lift_leaderboard
from repere.registry import load_registry_yaml
from repere.skills import SkillLoader, render_with_skill
from repere_suites.sta_lta import STALTAIntentExtractionSuite

REPO
"""
    ),
    md(
        """\
## 2. Load registry, suite, and skill

`config/models.yaml` ships with 13 cards across `nano`/`small`/`medium`/`big`/`cloud` tiers.
We pick three **small** cards and the `stalta-detection` skill. The suite is
the public 6-event STA/LTA intent-extraction benchmark.
"""
    ),
    code(
        """\
registry = load_registry_yaml(REPO / "config" / "models.yaml")
suite = STALTAIntentExtractionSuite()
skill = SkillLoader(skills_dir=REPO / ".github" / "skills").get("stalta-detection")

cards = [registry.get(mid) for mid in ("mistral:7b", "llama3.1:8b", "qwen2.5:7b")]
[(c.id, c.metadata.get("tier"), c.context_window) for c in cards]
"""
    ),
    md(
        """\
## 3. Build a `prompt → gold` lookup for the offline stub

The offline simulation uses each model's expected answer to construct a
realistic-looking response. We walk the suite once to capture
`{prompt: gold_dict}` so each adapter can produce the *correct* JSON for
whichever event it is being asked about.
"""
    ),
    code(
        """\
prompt_to_gold = {prompt: gold for (prompt, gold, _scorer) in suite.items()}
print(f"{len(prompt_to_gold)} prompts in the public sample suite")
print("Example gold for the first item:")
print(json.dumps(next(iter(prompt_to_gold.values())), indent=2))
"""
    ),
    md(
        """\
## 4. Define three different fake-model policies

Each policy returns a string given a prompt. Simulated quality differs by
model:

- **mistral:7b** — broken without the skill, partial credit with it.
- **llama3.1:8b** — gets the easy first item without help, partial elsewhere; full credit when the skill is loaded.
- **qwen2.5:7b** — already at ceiling; no lift expected.
"""
    ),
    code(
        """\
def correct(prompt):
    for p, gold in prompt_to_gold.items():
        if p == prompt or p in prompt:
            return json.dumps(gold)
    return "{}"

def partial(prompt):
    for p, gold in prompt_to_gold.items():
        if p == prompt or p in prompt:
            return json.dumps({**gold, "starttime": "wrong", "endtime": "also-wrong"})
    return "{}"

def policy_for(model_id):
    if model_id == "mistral:7b":
        return lambda p: partial(p) if "Use the guidance" in p else "I am unsure."
    if model_id == "llama3.1:8b":
        first = next(iter(prompt_to_gold))
        def _resp(p):
            if "Use the guidance" in p:
                return correct(p)
            return correct(p) if p == first else partial(p)
        return _resp
    return lambda p: correct(p)

def factory(card):
    return EchoAdapter(_card=card, response_fn=policy_for(card.id))

def render(prompt, mode):
    return render_with_skill(prompt, skill, mode=mode)
"""
    ),
    md(
        """\
## 5. Run the skill-lift benchmark

`LeaderboardRunner` iterates each card under `mode="none"` and `mode="full"`,
records a row per model, and we ask for a Markdown-style table.
"""
    ),
    code(
        """\
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

cols = ["model_id", "score_none", "score_full", "lift", "cost_full_usd"]
print(" | ".join(cols))
print("-+-".join("-" * len(c) for c in cols))
for r in rows:
    print(" | ".join(
        f"{getattr(r, c):.4f}" if isinstance(getattr(r, c), float) else str(getattr(r, c))
        for c in cols
    ))
"""
    ),
    md(
        """\
## 6. Export the leaderboard JSON

The same payload format is what the static GitHub-Pages leaderboard reads.
"""
    ),
    code(
        """\
output = REPO / "results" / "notebook_skill_lift.json"
output.parent.mkdir(parents=True, exist_ok=True)
payload = build_skill_lift_leaderboard(rows)
output.write_text(json.dumps(payload, indent=2) + "\\n")
print(f"Wrote {output}")
print(json.dumps(payload, indent=2)[:600], "...")
"""
    ),
    md(
        """\
---

## 7. (Optional) Run live against local Ollama

The cells above use `EchoAdapter` for determinism. To run the same benchmark
on real Ollama models, swap the `factory` for `OpenAICompatAdapter` pointed
at your local server. Make sure the models are pulled first:

```bash
ollama pull mistral:7b llama3.1:8b qwen2.5:7b
```

Uncomment the cell below and re-run section **5**.
"""
    ),
    code(
        """\
# def factory(card):
#     return OpenAICompatAdapter(
#         _card=card,
#         base_url="http://127.0.0.1:11434",
#         api_key=None,           # Ollama needs no key
#         default_max_tokens=512,
#         timeout_s=180.0,
#     )
"""
    ),
    md(
        """\
## What just happened, in one paragraph

You loaded a YAML model registry, picked three small-tier cards, attached a
skill that follows the Anthropic Agent Skills format, and ran the same
benchmark suite under two skill conditions for each model. The runner used a
shared `BudgetGuard` so the total spend across all models is capped, and
emitted a `SkillLiftRow` per model containing both quality scores and cost.
The exported JSON is the same shape consumed by the static leaderboard at
`site/`.
"""
    ),
]


def main(out: Path) -> None:
    notebook = {
        "cells": CELLS,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.10",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(notebook, indent=1) + "\n")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main(Path(__file__).parent / "01_skill_lift_quickstart.ipynb")
