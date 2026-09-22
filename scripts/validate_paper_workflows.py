"""Validate 'agentify the paper' annotations before they become benchmark items.

An annotation is a claim about how a paper was actually done. A bad one silently
becomes a wrong gold answer, which is worse than no eval at all — so check it:

  * every node is in the ontology (a term the model is never shown can never be matched)
  * every edge connects declared nodes
  * the workflow is acyclic and connected
  * physical-ordering invariants hold (no preprocessing before acquisition, ...)
  * a reference solution scores 1.0 against its own gold (the eval is self-consistent)

    pixi run -e full python scripts/validate_paper_workflows.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from repere_suites.orchestration.scorers import (  # noqa: E402
    make_scorer_from_spec,
)
from repere_suites.paper_workflow.items import (  # noqa: E402
    PaperWorkflowSuite,
    load_ontology,
    operation_ids,
)


def main() -> int:
    onto = load_ontology()
    known = set(operation_ids())
    problems: list[str] = []

    suite = PaperWorkflowSuite()
    papers = suite._papers()
    print(f"validating {len(papers)} annotated paper(s) "
          f"against {len(known)} ontology operations\n")

    for p in papers:
        pid = p["id"]
        wf = p["workflow"]
        nodes, edges = set(wf["nodes"]), wf["edges"]

        for n in nodes - known:
            problems.append(f"{pid}: node {n!r} not in ontology")
        for a, b in edges:
            if a not in nodes:
                problems.append(f"{pid}: edge tail {a!r} is not a declared node")
            if b not in nodes:
                problems.append(f"{pid}: edge head {b!r} is not a declared node")

        # Ordering invariants from the ontology (physical executability).
        for inv in onto.get("invariants", []):
            if inv.get("type") != "precondition" or inv.get("min_count", 1) < 1:
                continue
            if inv["agent"] in nodes and inv["requires_agent"] not in nodes:
                problems.append(
                    f"{pid}: has {inv['agent']!r} without {inv['requires_agent']!r} "
                    f"-- {inv.get('why', '')}"
                )

        # Self-consistency: the reference workflow must score 1.0 on its own gold.
        prompt, gold, spec, meta = suite._compose(p)
        scorer = make_scorer_from_spec(spec)
        calls = [
            {"id": f"s{i}", "agent": n,
             "deps": [f"s{wf['nodes'].index(a)}" for a, b in edges if b == n]}
            for i, n in enumerate(wf["nodes"])
        ]
        score = scorer(json.dumps({"calls": calls}), gold)
        flag = "provisional" if meta["provisional"] else "author-validated"
        status = "OK " if score > 0.999 else "BAD"
        print(f"  [{status}] {pid:32} tier={meta['tier']:6} {flag:16} "
              f"self-score={score:.3f}  ({len(nodes)} ops, {len(edges)} deps)")
        if score <= 0.999:
            problems.append(
                f"{pid}: reference workflow does not score 1.0 against its own gold "
                f"({score:.3f}) -- the annotation is internally inconsistent"
            )

    n_prov = sum(1 for p in papers if p.get("provisional"))
    print()
    if problems:
        print("PROBLEMS:")
        for x in problems:
            print(f"  - {x}")
        return 1
    print("all annotations valid.")
    if n_prov:
        print(f"WARNING: {n_prov} paper(s) are marked `provisional: true` — they were "
              "annotated from the abstract by the framework author, NOT by a domain "
              "author. Validate or replace them before publishing any number.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
