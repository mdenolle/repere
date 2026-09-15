"""Tests for corpus-backed literature retrieval (pure, offline, deterministic).

Covers the real OOI-RCA corpus loader, the cutoff-enforcing ranker, and the
leakage/fabrication audit — no ``inspect_ai`` and no network required.
"""

from __future__ import annotations

import json

import pytest

from frugalmind.agents import literature as lit

SHR_PLUMES = "10.1002/2016GC006250"  # Philip 2016, Southern Hydrate Ridge bubble plumes
DRIFT_2023 = "10.1029/2022EA002434"  # Sasagawa 2023, drift-corrected pressure 2018-2021
DRIFT_2016 = "10.1002/2016EA000190"  # Sasagawa 2016, drift-corrected pressure 2013-2014
WIND_2025 = "10.1121/10.0039811"  # Ragland 2025, wind-dependent ambient sound


def test_corpus_is_real_and_ids_unique():
    docs = lit.load_corpus()
    assert len(docs) >= 100
    ids = [d.id for d in docs]
    assert len(ids) == len(set(ids))
    assert all(d.year >= 2013 for d in docs)
    # Every id is a DOI (or an explicit no-DOI slug), never a synthetic key.
    assert all(d.id.startswith("10.") or d.id.startswith("nodoi:") for d in docs)
    assert sum(1 for d in docs if d.doi) >= 140


def test_corpus_carries_provenance():
    raw = json.loads(lit.corpus_path().read_text())
    assert raw["corpus_id"] == "ooi_rca_zotero"
    assert raw["source"]["repo"].endswith("mhemmett/arcada")
    assert len(raw["source"]["sha256"]) == 64
    assert raw["n_documents"] == len(raw["documents"])
    assert (
        "synthetic" not in raw["note"].lower() or "nothing here is synthetic" in raw["note"].lower()
    )


def test_document_citation_string():
    docs = {d.id: d for d in lit.load_corpus()}
    assert docs[DRIFT_2023].citation == "Sasagawa (2023), Earth and Space Science"


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
        "bubble plume time series Southern Hydrate Ridge water column methane Pinnacle",
        docs,
        top_k=5,
    )
    assert hits, "expected at least one hit"
    assert hits[0]["id"] == SHR_PLUMES
    assert hits[0]["first_author"] == "Philip"


def test_search_is_deterministic():
    docs = lit.load_corpus()
    q = "drift corrected seafloor pressure recorder deadweight tester quartz gauges"
    a = [h["id"] for h in lit.search_corpus(q, docs, top_k=5)]
    b = [h["id"] for h in lit.search_corpus(q, docs, top_k=5)]
    assert a == b
    assert DRIFT_2023 in a[:3] and DRIFT_2016 in a[:3]


def test_cutoff_excludes_post_cutoff_papers():
    docs = lit.load_corpus()
    q = "wind speed ambient sound hydrophone piecewise log-linear"
    unbounded = [h["id"] for h in lit.search_corpus(q, docs, top_k=10)]
    bounded = [h["id"] for h in lit.search_corpus(q, docs, cutoff_date="2020-01-01", top_k=10)]
    assert WIND_2025 in unbounded
    assert WIND_2025 not in bounded
    assert all(next(d for d in docs if d.id == i).year <= 2020 for i in bounded)


def test_no_match_returns_empty():
    docs = lit.load_corpus()
    assert lit.search_corpus("xylophone quantum banana", docs) == []


def test_leakage_flags_fabricated_and_post_cutoff_ids():
    docs = lit.load_corpus()
    audit = lit.retrieval_leakage(
        [SHR_PLUMES, WIND_2025, "10.9999/not-a-paper"], docs, cutoff_date="2020-01-01"
    )
    assert audit["fabricated"] == ["10.9999/not-a-paper"]
    assert audit["leaked"] == [WIND_2025]  # 2025 paper past a 2020 cutoff


def test_leakage_clean_when_within_cutoff():
    docs = lit.load_corpus()
    audit = lit.retrieval_leakage([SHR_PLUMES, DRIFT_2016], docs, cutoff_date="2020-01-01")
    assert audit == {"leaked": [], "fabricated": []}
