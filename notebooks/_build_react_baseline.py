"""Generator for the ReAct multi-step agent baseline notebook (P2.4).

Run once to (re)generate ``03_react_baseline.ipynb``.

The notebook is a **stub** in the sense that it does not call a paid
provider in CI — the default code path uses InspectAI's ``mockllm`` model,
which returns a canned tool call sequence. A second section at the end
shows the one-line swap to ``anthropic/claude-haiku-4-5-20251001`` (or any
Inspect-supported model) for live runs.

Reproducible by convention: this script is the source of truth, the
``.ipynb`` is the artefact.
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
# Repère — ReAct multi-step agent baseline (P2.4)

This notebook walks through the **ReAct baseline solver** that lets a model
choose between calling tools and submitting an answer on the STA/LTA suites.
It is the Repère counterpart to AstaBench's reference baseline and the
direct comparison point for `generate` (single-shot) runs on the cost-Pareto chart.

What you'll see:

1. The three Inspect tools the agent has access to (`fdsn_get_waveforms`,
   `python_session`, `record_submit`).
2. The `stalta_react` solver — a thin wrapper around Inspect's `basic_agent`.
3. A **mock-model dry run** that exercises the solver end-to-end *without*
   touching a paid provider. This is the path CI uses.
4. The one-line swap to a real provider for a live run.

> Prerequisites: `pip install -e ".[eval]"` from the repo root. `inspect_ai`
> is **optional**; without it, this notebook will not import.
"""
    ),
    md("## 0. Confirm the eval extra is installed"),
    code(
        """\
# Fail fast with a clear message if `inspect_ai` is missing.
try:
    import inspect_ai
except ImportError as exc:
    raise ImportError(
        "This notebook needs the `[eval]` extra. Run:\\n"
        "    pip install -e \\".[eval]\\"\\n"
        "from the repo root, then restart this kernel."
    ) from exc

print("inspect_ai version:", inspect_ai.__version__)
"""
    ),
    md(
        """\
## 1. The three tools the agent can call

`repere.agents.tools` wraps three callables as `@tool` decorators. Each is
**stateless**, **provider-agnostic**, and never raises — every failure mode is
returned as JSON so the agent can read it and decide what to do next.
"""
    ),
    code(
        """\
from repere.agents import stalta_tools_dict

# Static descriptor — does not import inspect_ai's runtime types.
for name, desc in stalta_tools_dict().items():
    print(f"  - {name}: {desc}")
"""
    ),
    code(
        """\
# Inspect-side instantiations. Each factory returns an inspect_ai.tool.Tool.
from repere.agents.tools import all_tools

tools = all_tools()
for t in tools:
    print(type(t).__name__, "—", getattr(t, "__name__", repr(t)))
"""
    ),
    md(
        """\
### Smoke test: `python_session` round-trips a snippet through the sandbox

The sandbox is the same subprocess sandbox the suite scorers use, so model
code paths and scoring code paths exercise the same runtime.
"""
    ),
    code(
        """\
import asyncio, json
from repere.agents.tools import python_session

sess = python_session()
raw = asyncio.run(sess(code="record(answer=2+2)\\nprint('hello from sandbox')", timeout_s=20.0))
print(json.dumps(json.loads(raw), indent=2))
"""
    ),
    md(
        """\
## 2. The ReAct solver

`stalta_react()` returns an Inspect `Solver` that wraps `basic_agent` with the
three tools and a STA/LTA-specific system prompt. The solver is a single object
you hand to `inspect eval --solver` or call programmatically.

Default knobs:

  - `max_attempts=1` — AstaBench's convention; raise for noisier models.
  - `message_limit=24` — proxy for cost; catches a runaway tool loop.
  - `system_prompt=None` — use the built-in STA/LTA prompt. Pass a string to override
    (e.g., to prepend a Repère skill).
"""
    ),
    code(
        """\
from repere.agents.react import stalta_react

solver = stalta_react()
print("solver type:", type(solver).__name__)
print("solver callable:", callable(solver))
"""
    ),
    md(
        """\
## 3. Mock-model dry run

We use Inspect's `mockllm/model` to verify the wiring without paying a provider.
`mockllm` returns a fixed string — that's enough to confirm the solver loop
starts, the tools are advertised, and a submission round-trips.

For a *real* end-to-end behavioural test you'd swap to a live provider — see §4.
"""
    ),
    code(
        """\
# A one-sample Inspect task built directly from a `fetch_code` item.
from inspect_ai import eval as inspect_eval
from repere_suites.sta_lta.inspect_tasks import fetch_code

task = fetch_code(split="validation")
print("dataset size:", len(list(task.dataset)))
"""
    ),
    code(
        """\
# Run the solver against `mockllm/model`. This does NOT touch a paid provider.
# It also doesn't exercise tool selection (mockllm returns one fixed string),
# but it does confirm the solver constructs and the harness wires it up.
#
# NOTE: even mockllm runs spin up worker tasks. Keep `limit=1` so this stays
# under a few seconds. If your environment doesn't allow background eval
# workers, comment this cell out — it's not required for the rest of the
# notebook to make sense.
try:
    logs = inspect_eval(
        task,
        model="mockllm/model",
        solver=stalta_react(message_limit=4),
        limit=1,
    )
    print("eval completed; log count:", len(logs))
except Exception as exc:
    print(f"(skipping mock eval: {type(exc).__name__}: {exc})")
"""
    ),
    md(
        """\
## 4. Swap in a real model (one line)

To run the same solver against a live provider, change the `model=` string.
Inspect supports `anthropic/...`, `openai/...`, `ollama/...`, and any
OpenAI-compatible endpoint via `openai/...` with a custom base URL. Make sure
the matching credential env var is set (e.g. `ANTHROPIC_API_KEY`).

```python
# Live run — costs money. Uncomment when you're ready.
# logs = inspect_eval(
#     fetch_code(split="validation"),
#     model="anthropic/claude-haiku-4-5-20251001",
#     solver=stalta_react(),
# )
```

For CLI use, the same solver is addressable as:

```bash
inspect eval src/repere_suites/sta_lta/inspect_tasks.py@fetch_code \\
  --solver src/repere/agents/react.py@stalta_react \\
  --model anthropic/claude-haiku-4-5-20251001
```

The resulting log can be inspected with `inspect view`.
"""
    ),
    md(
        """\
## 5. Where this fits on the cost-Pareto chart

Each ReAct run produces (cost, score) pairs that go straight into the static
site's Pareto panel — the same chart `generate` (single-shot) runs feed into.
The point of P2.4 is to make the ReAct vs single-shot trade-off **visible**,
not to assert one is better than the other.

When you run a real comparison, write the resulting JSON into `results/`
and re-run `scripts/build_site_data.py` to refresh `site/data/leaderboard.json`.
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
    main(Path(__file__).parent / "03_react_baseline.ipynb")
