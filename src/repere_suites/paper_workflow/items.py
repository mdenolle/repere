"""'Agentify the paper' — research-workflow evaluation (Family 3).

Given a paper, an orchestrator must emit the RESEARCH WORKFLOW that produces it:
a DAG over the closed operation vocabulary in `ontology.yaml`. It is scored on
the graph — node F1, edge F1, frugality — against the author-annotated reference
workflow, with no LLM judge anywhere in the loop.

This is the research-workflow family's real evaluation. Three properties make it
work where "grade this research plan" would not:

* **Closed vocabulary.** A free-text plan cannot be scored; a DAG over a fixed
  alphabet can. See ontology.yaml for the cost of that choice.
* **Author-annotated gold.** Only someone who did the work knows the workflow.
* **Hallucinated methodology is penalised.** Adding `forward_model` to a paper
  that ran no simulations costs node precision — negative-case discipline applied
  to research planning.

Contamination: published papers are in the training data, so they are the
*validation* split. Unpublished, in-preparation papers are in no training corpus
and are therefore the only honest measurement of whether a model can *plan*
research rather than *recall* it; they are the hidden `test` split.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import yaml

from repere import DenolleGroupSuite, TaskKind
from repere.export import BenchmarkRow
from repere_suites.orchestration.scorers import make_scorer_from_spec

_HERE = Path(__file__).parent
ONTOLOGY_PATH = Path(os.environ.get("FM_PW_ONTOLOGY", _HERE / "ontology.yaml"))
PAPERS_PATH = Path(os.environ.get("FM_PW_PAPERS", _HERE / "papers.yaml"))

# Unpublished papers (the honest test split) never live in git.
_REPO = _HERE.resolve().parents[2]
PRIVATE_DIR = Path(os.environ.get("FM_EVAL_DATA_DIR", _REPO / "data" / "private"))
HIDDEN_PAPERS_PATH = PRIVATE_DIR / "paper_workflow_test.yaml"

VALID_SPLITS = ("validation", "test")
VALID_TIERS = ("easy", "medium", "hard")


def load_ontology() -> dict:
    return yaml.safe_load(ONTOLOGY_PATH.read_text())


def operation_ids() -> list[str]:
    return [o["id"] for o in load_ontology()["operations"]]


def _resolve_split(split: str | None) -> str | None:
    if split is None:
        env = os.environ.get("FM_PW_SPLIT")
        if env in (None, "", "all"):
            return None
        split = env
    if split not in VALID_SPLITS:
        raise ValueError(f"split must be one of {VALID_SPLITS} or None; got {split!r}")
    return split


def _load_papers(split: str | None = None) -> list[dict]:
    papers = list(yaml.safe_load(PAPERS_PATH.read_text())["papers"])

    # The hidden (unpublished) split, when it has been pulled.
    if HIDDEN_PAPERS_PATH.exists():
        hidden = yaml.safe_load(HIDDEN_PAPERS_PATH.read_text()) or {}
        papers.extend(hidden.get("papers", []))

    known = set(operation_ids())
    for p in papers:
        for key in ("id", "tier", "split", "visibility", "title", "abstract", "workflow"):
            if key not in p:
                raise ValueError(f"paper {p.get('id')!r} missing key {key!r}")
        if p["tier"] not in VALID_TIERS:
            raise ValueError(f"paper {p['id']!r}: bad tier {p['tier']!r}")
        # An annotation using a term outside the ontology can never be matched by
        # a model that is only shown the ontology — fail loudly at load.
        for n in p["workflow"]["nodes"]:
            if n not in known:
                raise ValueError(
                    f"paper {p['id']!r}: node {n!r} is not in the ontology. "
                    "Extend ontology.yaml deliberately, or fix the annotation."
                )

    split = _resolve_split(split)
    if split == "test" and not any(p["split"] == "test" for p in papers):
        raise FileNotFoundError(
            "the hidden (unpublished-paper) test split is not available locally.\n"
            f"  expected: {HIDDEN_PAPERS_PATH}\n"
            "  pull it:  pixi run -e full python scripts/pull_eval_data.py\n"
            "  Published papers are in the models' training data; only the "
            "unpublished split measures planning rather than recall."
        )
    if split is not None:
        papers = [p for p in papers if p["split"] == split]
    return papers


class PaperWorkflowSuite(DenolleGroupSuite):
    """Paper -> research workflow DAG, scored against the author's own workflow."""

    task_kind = TaskKind.ORCHESTRATION
    dataset_id = "paper_workflow"
    suite_id = "agentify_the_paper"
    version = "v0.1"

    def __init__(self, *, split: str | None = None) -> None:
        self.split = _resolve_split(split)

    def _papers(self) -> list[dict]:
        return _load_papers(self.split)

    def _compose(self, p: dict) -> tuple[str, Any, dict, dict]:
        onto = load_ontology()
        vocab = "\n".join(
            f"  {o['id']:28} {o['description']}" for o in onto["operations"]
        )

        # Tier controls how much of the paper the model is allowed to see. The
        # `hard` tier withholds the abstract, so the model must DESIGN the
        # workflow rather than extract it.
        tier = p["tier"]
        if tier == "hard":
            given = f"Title:\n  {' '.join(p['title'].split())}\n"
        else:
            given = (
                f"Title:\n  {' '.join(p['title'].split())}\n\n"
                f"Abstract:\n  {' '.join(p['abstract'].split())}\n"
            )
            if tier == "easy" and p.get("methods"):
                given += f"\nMethods:\n  {' '.join(p['methods'].split())}\n"

        prompt = (
            "You are the orchestrator of a geophysics research group. Given the "
            "paper below, produce the RESEARCH WORKFLOW that would generate it: "
            "the operations to run, and the dependencies between them.\n\n"
            f"{given}\n"
            "Use ONLY these operations:\n"
            f"{vocab}\n\n"
            "Emit the workflow as a JSON object. Each call has an id, an "
            "operation name from the list, and the ids it depends on:\n"
            '  {"calls": [\n'
            '     {"id": "s1", "agent": "acquire_waveforms", "deps": []},\n'
            '     {"id": "s2", "agent": "preprocess_waveforms", "deps": ["s1"]}\n'
            "  ]}\n\n"
            "Include only the steps this paper actually requires — inventing "
            "methodology the paper did not perform is penalised. Return only the "
            "JSON object."
        )

        wf = p["workflow"]
        gold = {"nodes": wf["nodes"], "edges": wf["edges"]}
        scorer_spec = {
            "name": "trajectory_dag",
            "config": {
                "expected_agents": wf["nodes"],
                "expected_edges": wf["edges"],
                "max_calls": wf.get("max_calls", len(wf["nodes"]) + 3),
            },
        }
        meta = {
            "paper_id": p["id"],
            "tier": tier,
            "provisional": bool(p.get("provisional", False)),
            "cutoff_date": p.get("cutoff_date"),
            "n_expected_ops": len(wf["nodes"]),
        }
        return prompt, gold, scorer_spec, meta

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for p in self._papers():
            prompt, gold, spec, _ = self._compose(p)
            yield (prompt, gold, make_scorer_from_spec(spec))

    def export_rows(self) -> Iterable[BenchmarkRow]:
        for p in self._papers():
            prompt, gold, spec, meta = self._compose(p)
            yield BenchmarkRow(
                id=f"{self.dataset_id}/{self.suite_id}/{p['id']}",
                dataset_id=self.dataset_id,
                suite_id=self.suite_id,
                version=self.version,
                task_kind=self.task_kind.value,
                split=p["split"],
                visibility=p["visibility"],
                prompt=prompt,
                gold=gold,
                scorer_spec=spec,
                metadata=meta,
            )


ALL_SUITES = (PaperWorkflowSuite,)
