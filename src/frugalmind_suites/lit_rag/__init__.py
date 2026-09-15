"""Literature / RAG / translation suites (Family 1), verifiable-core.

Decomposes "open-ended" literature tasks into pieces scorable against a
reference with no LLM in the loop, over the real OOI Regional Cabled Array
corpus: known-item retrieval (MRR / nDCG), abstention (a proper scoring rule
over answerable and unanswerable queries), grounded QA (citation validity /
precision / recall + fact coverage) and translation term-preservation. See
``docs/lit_rag_scorers.md``.

InspectAI tasks live in ``inspect_tasks.py`` / ``agent_tasks.py`` (optional
``inspect-ai`` extra); the scorers and suites here have no such dependency.
"""

from __future__ import annotations

from . import items, scorers
from .items import (
    ALL_SUITES,
    HIDDEN_TRUTH_PATH,
    TRUTH_PATH,
    LitRagAbstentionSuite,
    LitRagGroundedQASuite,
    LitRagKnownItemSuite,
    LitRagRetrievalSuite,
    LitRagTranslationSuite,
)

__all__ = [
    "ALL_SUITES",
    "HIDDEN_TRUTH_PATH",
    "TRUTH_PATH",
    "LitRagAbstentionSuite",
    "LitRagGroundedQASuite",
    "LitRagKnownItemSuite",
    "LitRagRetrievalSuite",
    "LitRagTranslationSuite",
    "items",
    "scorers",
]
