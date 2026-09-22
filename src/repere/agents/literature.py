"""Corpus-backed literature retrieval — the reproducible core of the RAG tool.

Why not a live ``web_search``? The lit_rag retrieval scorer grades a ranked
list of document ids against a gold set with nDCG (see
``repere_suites/lit_rag/scorers.py``). That only works over a **frozen,
versioned corpus with stable ids**. Live web search is non-deterministic
(breaks the gold match), un-date-boundable (breaks the AstaBench cutoff
contract in ``ROADMAP.md``), and returns URLs rather than the stable ids the
scorer parses. So retrieval here runs over a snapshotted corpus:

* :func:`load_corpus` reads a JSON corpus (default: the seed OOI/COZI fixture,
  overridable with ``REPERE_LITRAG_CORPUS``).
* :func:`search_corpus` ranks documents by a deterministic lexical score and
  **enforces the cutoff** — a paper published after ``cutoff_date`` is never
  returned, so the agent physically cannot cite post-cutoff work.
* :func:`retrieval_leakage` is a defensive audit: given the ids an agent
  submitted, how many were published after the cutoff. In a correct run this
  is always 0 (the tool filters), but it catches ids the model *invented*.

Everything here is pure Python stdlib — no ``inspect_ai``, no network — so it
is deterministic, offline, and unit-testable. The Inspect ``@tool`` wrapper
lives in :mod:`repere.agents.lit_tools`.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Default corpus fixture. Replace its contents with the group's real
# OOI/COZI papers; the schema and tooling stay the same.
_DEFAULT_CORPUS = (
    Path(__file__).resolve().parents[2]
    / "repere_suites"
    / "lit_rag"
    / "data"
    / "ooi_corpus.json"
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Document:
    """One corpus document. ``id`` is the stable citation key the scorer uses."""

    id: str
    title: str
    abstract: str
    year: int
    published: str | None = None  # ISO date "YYYY-MM-DD"; falls back to year
    doi: str | None = None
    keywords: tuple[str, ...] = ()

    @property
    def searchable_text(self) -> str:
        return " ".join([self.title, self.abstract, " ".join(self.keywords)])


def corpus_path(path: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the corpus path: explicit arg > ``REPERE_LITRAG_CORPUS`` > default."""
    if path is not None:
        return Path(path)
    env = os.environ.get("REPERE_LITRAG_CORPUS")
    return Path(env) if env else _DEFAULT_CORPUS


def load_corpus(path: str | os.PathLike[str] | None = None) -> list[Document]:
    """Load and validate a JSON corpus into :class:`Document` objects.

    The file is ``{"corpus_id": str, "documents": [ {id,title,abstract,year,
    ...}, ... ]}``. Ids must be unique — a duplicate id would make nDCG
    scoring ambiguous, so we raise rather than silently dedupe.
    """
    p = corpus_path(path)
    if not p.exists():
        raise FileNotFoundError(f"corpus not found: {p}")
    data = json.loads(p.read_text())
    docs: list[Document] = []
    seen: set[str] = set()
    for row in data.get("documents", []):
        doc_id = str(row["id"])
        if doc_id in seen:
            raise ValueError(f"duplicate document id in corpus: {doc_id!r}")
        seen.add(doc_id)
        docs.append(
            Document(
                id=doc_id,
                title=str(row.get("title", "")),
                abstract=str(row.get("abstract", "")),
                year=int(row["year"]),
                published=row.get("published"),
                doi=row.get("doi"),
                keywords=tuple(str(k) for k in row.get("keywords", [])),
            )
        )
    return docs


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _published_after(doc: Document, cutoff_date: str | None) -> bool:
    """True if ``doc`` was published strictly after ``cutoff_date``.

    Compares full ISO dates when both are available (lexicographic works for
    ``YYYY-MM-DD``); otherwise compares publication *year* to the cutoff year.
    A missing cutoff means "no bound" → never after.
    """
    if not cutoff_date:
        return False
    if doc.published:
        return doc.published > cutoff_date
    cutoff_year = int(cutoff_date[:4])
    return doc.year > cutoff_year


def _score(query_tokens: list[str], doc: Document) -> float:
    """Deterministic lexical relevance: summed term frequency of query tokens.

    Simple and reproducible on purpose — the benchmark's job is to measure the
    *agent's* ranking behaviour over stable tool output, not to ship a
    state-of-the-art retriever. Swap in BM25/embeddings later without changing
    the tool surface or the scorer.
    """
    if not query_tokens:
        return 0.0
    doc_tokens = _tokenize(doc.searchable_text)
    if not doc_tokens:
        return 0.0
    counts: dict[str, int] = {}
    for tok in doc_tokens:
        counts[tok] = counts.get(tok, 0) + 1
    return float(sum(counts.get(q, 0) for q in set(query_tokens)))


def search_corpus(
    query: str,
    documents: list[Document],
    *,
    cutoff_date: str | None = None,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Rank ``documents`` for ``query``, cutoff-filtered, best first.

    Returns up to ``top_k`` hits as JSON-ready dicts
    ``{id, title, abstract, year, doi, score}``. Documents published after
    ``cutoff_date`` are dropped *before* ranking. Ties break by id ascending
    so the ordering is fully deterministic across runs and machines.
    """
    query_tokens = _tokenize(query)
    eligible = [d for d in documents if not _published_after(d, cutoff_date)]
    scored = [(d, _score(query_tokens, d)) for d in eligible]
    # Keep only positive-relevance hits; sort by score desc then id asc.
    hits = [(d, s) for d, s in scored if s > 0.0]
    hits.sort(key=lambda ds: (-ds[1], ds[0].id))
    out: list[dict[str, Any]] = []
    for doc, score in hits[: max(0, top_k)]:
        out.append(
            {
                "id": doc.id,
                "title": doc.title,
                "abstract": doc.abstract,
                "year": doc.year,
                "doi": doc.doi,
                "score": score,
            }
        )
    return out


def retrieval_leakage(
    submitted_ids: list[str],
    documents: list[Document],
    *,
    cutoff_date: str | None,
) -> dict[str, Any]:
    """Audit submitted ids for cutoff leakage and fabrication.

    Returns ``{leaked: [ids after cutoff], fabricated: [ids not in corpus]}``.
    In a correct agent run both lists are empty — non-empty ``fabricated`` is
    the retrieval analog of a hallucinated citation; non-empty ``leaked``
    means the model surfaced a post-cutoff id it must not have known.
    """
    by_id = {d.id: d for d in documents}
    leaked: list[str] = []
    fabricated: list[str] = []
    for doc_id in submitted_ids:
        doc = by_id.get(str(doc_id))
        if doc is None:
            fabricated.append(str(doc_id))
        elif _published_after(doc, cutoff_date):
            leaked.append(str(doc_id))
    return {"leaked": leaked, "fabricated": fabricated}


__all__ = [
    "Document",
    "corpus_path",
    "load_corpus",
    "search_corpus",
    "retrieval_leakage",
]
