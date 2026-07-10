"""Literature / RAG / translation suites (Family 1), verifiable-core.

Decomposes "open-ended" literature tasks into pieces scorable against a
reference with no LLM in the loop: retrieval (recall@k / MRR / nDCG),
translation term-preservation, and grounded-QA citation support. See
``docs/lit_rag_scorers.md``.

InspectAI tasks live in ``inspect_tasks.py`` (optional ``inspect-ai`` extra);
the scorers and suites here have no such dependency.
"""

from __future__ import annotations

from . import items, scorers
from .items import (
    ALL_SUITES,
    TASKS_PATH,
    LitRagGroundedQASuite,
    LitRagRetrievalSuite,
    LitRagTranslationSuite,
)

__all__ = [
    "ALL_SUITES",
    "TASKS_PATH",
    "LitRagGroundedQASuite",
    "LitRagRetrievalSuite",
    "LitRagTranslationSuite",
    "items",
    "scorers",
]
