"""'Agentify the paper' — research-workflow evaluation (Family 3).

Given a paper, an orchestrator emits the research workflow that produces it, as a
DAG over a closed operation vocabulary. Scored on the graph (node F1, edge F1,
frugality) against the author-annotated reference, with no LLM judge.

Published papers are the `validation` split (they are in the training data).
Unpublished, in-preparation papers are the hidden `test` split — the only honest
measurement of whether a model can PLAN research rather than RECALL it.
"""

from __future__ import annotations

from . import items
from .items import (
    ALL_SUITES,
    ONTOLOGY_PATH,
    PAPERS_PATH,
    PaperWorkflowSuite,
    load_ontology,
    operation_ids,
)

__all__ = [
    "ALL_SUITES",
    "ONTOLOGY_PATH",
    "PAPERS_PATH",
    "PaperWorkflowSuite",
    "items",
    "load_ontology",
    "operation_ids",
]
