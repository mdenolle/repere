"""Candidate shortlists with hard distractors, for retrieval items.

A retrieval item shows the model k candidate documents and asks for the
relevant ones. Drawing the k − |gold| distractors at random makes the task
trivial: queries name distinctive entities, and if no distractor shares them,
keyword matching alone finds the gold. ``hard_shortlist`` picks the
distractors most confusable with the gold instead (Jaccard overlap of content
words), so a model has to discriminate on what a document actually says.

Corpus-agnostic: it takes ``(id, text)`` pairs, so it serves the RCA Atlas
chunks (ROADMAP P3.7) and any other corpus. Ported from the archived branch
``archive/lit-rag-ooi-rca-2026-09`` (2026-09-15).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping

STOPWORDS = frozenset(
    "a an the of for and or to in on with we our this that is are be by from as at "
    "using use used propose proposed present presents new novel method methods "
    "results show shows can it its their they which than then also more most such "
    "these those has have been was were will would".split()
)


def content_terms(text: str) -> set[str]:
    """Lower-cased alphanumeric words longer than three letters, minus stopwords."""
    words = "".join(c if c.isalnum() else " " for c in text.lower()).split()
    return {w for w in words if len(w) > 3 and w not in STOPWORDS}


def terms_by_id(docs: Iterable[tuple[str, str]]) -> dict[str, set[str]]:
    """``{id: content_terms(text)}`` for ``(id, text)`` pairs."""
    return {doc_id: content_terms(text) for doc_id, text in docs}


def _hash(seed: str, doc_id: str) -> str:
    return hashlib.sha256(f"{seed}|{doc_id}".encode()).hexdigest()


def hard_shortlist(
    reference_terms: set[str],
    pool: Mapping[str, set[str]],
    *,
    include: list[str],
    k: int,
    seed: str,
) -> list[str]:
    """``include`` plus the ``k − len(include)`` pool ids most similar to the reference.

    ``reference_terms`` is usually the content terms of the gold document(s)
    or of the query. Deterministic: similarity ties break on a hash of
    ``seed`` and the id, and the returned order is a hash too, so the gold
    does not always sit in the same slot.
    """
    if k < len(include):
        raise ValueError(f"k={k} is smaller than the {len(include)} ids that must be included")
    missing = [i for i in include if i not in pool]
    if missing:
        raise KeyError(f"ids to include are not in the pool: {missing}")

    def similarity(terms: set[str]) -> float:
        union = reference_terms | terms
        return len(reference_terms & terms) / len(union) if union else 0.0

    others = sorted(
        (i for i in pool if i not in include),
        key=lambda i: (-similarity(pool[i]), _hash(seed, i)),
    )
    picked = [*include, *others[: k - len(include)]]
    return sorted(picked, key=lambda i: _hash(seed, i))


__all__ = ["STOPWORDS", "content_terms", "hard_shortlist", "terms_by_id"]
