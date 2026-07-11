"""Tests for corpus-backed literature retrieval (pure, offline, deterministic).

Covers the seed OOI/COZI corpus loader, the cutoff-enforcing ranker, and the
leakage/fabrication audit — no ``inspect_ai`` and no network required.
"""

from __future__ import annotations

import json

import pytest

from frugalmind.agents import literature as lit


def test_seed_corpus_loads_and_ids_unique():
    docs = lit.load_corpus()
    assert len(docs) >= 5
    ids = [d.id for d in docs]
    assert len(ids) == len(set(ids))
    assert all(d.year > 0 for d in docs)


def test_duplicate_ids_raise(tmp_path):
    bad = tmp_path / "dup.json"
    bad.write_text(
        json.dumps(
            {
                "documents": [
                    {"id": "X1", "title": "a", "abstract": "", "year": 2000},
                    {"id": "X1", "title": "b", "abstract": "", "year": 2001},
                ]
            }
        )
    )
    with pytest.raises(ValueError):
        lit.load_corpus(bad)


def test_missing_corpus_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        lit.load_corpus(tmp_path / "nope.json")


def test_search_ranks_relevant_doc_first():
    docs = lit.load_corpus()
    hits = lit.search_corpus(
        "methane hydrate bubble plume Southern Hydrate Ridge", docs, top_k=5
    )
    assert hits, "expected at least one hit"
    assert hits[0]["id"] == "OOI-002"


def test_search_is_deterministic():
    docs = lit.load_corpus()
    q = "ambient noise cross-correlation velocity monitoring"
    a = [h["id"] for h in lit.search_corpus(q, docs, top_k=5)]
    b = [h["id"] for h in lit.search_corpus(q, docs, top_k=5)]
    assert a == b
    assert "OOI-003" in a


def test_cutoff_excludes_post_cutoff_papers():
    docs = lit.load_corpus()
    # OOI-008 (machine learning, 2023) must be filtered out before 2019.
    q = "machine learning detection of seismic events cabled array"
    unbounded = [h["id"] for h in lit.search_corpus(q, docs, top_k=10)]
    bounded = [
        h["id"] for h in lit.search_corpus(q, docs, cutoff_date="2019-01-01", top_k=10)
    ]
    assert "OOI-008" in unbounded
    assert "OOI-008" not in bounded


def test_no_match_returns_empty():
    docs = lit.load_corpus()
    assert lit.search_corpus("xylophone quantum banana", docs) == []


def test_leakage_flags_fabricated_and_post_cutoff_ids():
    docs = lit.load_corpus()
    audit = lit.retrieval_leakage(
        ["OOI-002", "OOI-008", "OOI-999"], docs, cutoff_date="2019-01-01"
    )
    assert audit["fabricated"] == ["OOI-999"]
    assert audit["leaked"] == ["OOI-008"]  # 2023 paper past a 2019 cutoff


def test_leakage_clean_when_within_cutoff():
    docs = lit.load_corpus()
    audit = lit.retrieval_leakage(["OOI-002", "OOI-003"], docs, cutoff_date="2020-01-01")
    assert audit == {"leaked": [], "fabricated": []}
