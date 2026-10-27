"""RCA Atlas gold -> attribution scorer spec.

Synthetic gold records only; the one test that reads real Atlas gold uses the
verified local cache from scripts/pull_atlas.py and is skipped without it.
"""

from __future__ import annotations

import pytest

from repere_suites.atlas import AtlasHashMismatch, load_atlas
from repere_suites.atlas.answers import answer_attribution_spec, is_ranked, relevant_source_ids
from repere_suites.lit_rag.scorers import make_scorer_from_spec

GOLD = {
    "review_status": "corpus_verified",
    "required_entity_ids": ["PREST"],
    "required_citations": [
        {"source_id": "SRC-PDF-1", "url": ""},
        {"source_id": "repo:example@abc", "url": "https://example.org/repo/tree/abc/"},
    ],
}
SOURCES = [
    {"id": "INSTR-1", "url": "https://example.org/instrument/prest/"},
    {"id": "SRC-PDF-1", "url": ""},
    {"id": "CHUNK-9", "url": "https://example.org/repo/tree/abc"},
]


def test_required_citations_match_by_id_or_url():
    assert relevant_source_ids(GOLD, SOURCES) == ["SRC-PDF-1", "CHUNK-9"]


def test_unlisted_required_source_stays_relevant_so_recall_shows_the_miss():
    assert relevant_source_ids(GOLD, SOURCES[:1]) == ["SRC-PDF-1", "repo:example@abc"]


def test_spec_scores_an_atlas_style_answer():
    scorer = make_scorer_from_spec(answer_attribution_spec(GOLD, SOURCES))
    b = scorer.breakdown("Prest records seafloor pressure [2] and the code is public [3]. See also [5].")
    assert b["fabricated"] == ["#5"]
    assert b["citation_recall"] == 1.0
    assert b["fact_coverage"] == 1.0


def test_title_only_citation_matches_on_title():
    gold = {"required_citations": [{"title": "Cable Map  "}]}
    assert relevant_source_ids(gold, [{"id": "X", "title": "cable map"}]) == ["X"]
    assert relevant_source_ids(gold, [{"id": "X", "title": "other"}]) == ["title:cable map"]


def test_spec_needs_the_source_list():
    with pytest.raises(ValueError):
        answer_attribution_spec(GOLD, [])


def test_only_corpus_verified_gold_is_ranked():
    assert is_ranked(GOLD)
    assert not is_ranked({**GOLD, "review_status": "requires_human_review"})


def test_adapter_handles_every_pinned_gold_record():
    try:
        rows = load_atlas("rca_eval_gold")
    except (FileNotFoundError, AtlasHashMismatch):
        pytest.skip("Atlas gold not pulled; run scripts/pull_atlas.py")
    for gold in rows:
        needs = gold.get("required_citations") or []
        listed = [
            {"id": f"S{i}", "url": c.get("url"), "title": c.get("title")} if not c.get("source_id")
            else {"id": c["source_id"], "url": c.get("url")}
            for i, c in enumerate(needs)
        ] or [{"id": "placeholder"}]
        spec = answer_attribution_spec(gold, listed)
        assert callable(make_scorer_from_spec(spec))
        # Every required citation resolves to a listed source when all are listed.
        assert set(spec["config"]["relevant_sources"]) <= {s["id"] for s in listed}
        assert len(spec["config"]["relevant_sources"]) == len(needs)
