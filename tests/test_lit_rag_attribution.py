"""Attribution and abstention scorers, citation extraction, and the shortlist.

Ported from the archived branch archive/lit-rag-ooi-rca-2026-09, plus the
numbered-citation form RCA Atlas answers use. Every id here is synthetic or a
public DOI; no RCA Atlas row appears in this file.
"""

from __future__ import annotations

import pytest

from repere_suites.lit_rag.scorers import (
    ABSTAIN_SENTINEL,
    attribution_breakdown,
    extract_citations,
    is_abstention,
    make_abstention_scorer,
    make_attribution_scorer,
    make_scorer_from_spec,
)
from repere_suites.lit_rag.shortlist import content_terms, hard_shortlist, terms_by_id

SRC = ["10.1126/science.aah5563", "10.1130/G39978.1", "10.1126/science.aah4666"]


# --------------------------------------------------------------------------- #
# citation extraction
# --------------------------------------------------------------------------- #
def test_extract_citations_dois_and_keys():
    text = (
        "Onset was 24 April 2015 [10.1126/science.aah5563]. Ring faults slipped "
        "(doi:10.1130/G39978.1) and see https://doi.org/10.1029/2020JB019356. "
        "Also [S2] and again [10.1126/science.aah5563]."
    )
    assert extract_citations(text) == [
        "10.1126/science.aah5563",
        "10.1130/g39978.1",
        "10.1029/2020jb019356",
        "s2",
    ]


def test_bare_numbers_are_ignored_without_a_source_list():
    assert extract_citations("See [1] and [2-3].") == []


def test_numbered_citations_resolve_ranges_lists_and_out_of_range():
    listed = ["SRC-A", "SRC-B", "SRC-C"]
    text = "Pressure [1]. Drift [2-3]. Again [1, 3]. Invented [7]."
    assert extract_citations(text, numbered_sources=listed) == ["src-a", "src-b", "src-c", "#7"]


def test_abstention_requires_sentinel_and_no_citation():
    assert is_abstention(ABSTAIN_SENTINEL)
    assert is_abstention(f"  {ABSTAIN_SENTINEL}\n")
    assert not is_abstention(f"{ABSTAIN_SENTINEL} but maybe [10.1126/science.aah5563]")
    assert not is_abstention("I don't know.")


# --------------------------------------------------------------------------- #
# attribution
# --------------------------------------------------------------------------- #
def test_attribution_perfect_answer():
    scorer = make_attribution_scorer(
        valid_sources=SRC, relevant_sources=[SRC[0]], required_terms=["24 April 2015", "ring fault"]
    )
    ans = "The eruption began on 24 April 2015 and inflation was taken up by a ring fault [10.1126/science.aah5563]."
    assert scorer(ans, None) == pytest.approx(1.0)
    b = scorer.breakdown(ans)
    assert b["citation_validity"] == b["citation_recall"] == b["fact_coverage"] == 1.0
    assert b["fabricated"] == [] and not b["abstained"]


def test_attribution_fabricated_citation_is_visible_and_costly():
    scorer = make_attribution_scorer(
        valid_sources=SRC, relevant_sources=[SRC[0]], required_terms=["24 April 2015"]
    )
    ans = "It began on 24 April 2015 [10.1126/science.aah5563] as reviewed in [10.9999/made-up]."
    b = scorer.breakdown(ans)
    assert b["fabricated"] == ["10.9999/made-up"]
    assert b["citation_validity"] == pytest.approx(0.5)
    assert scorer(ans, None) == pytest.approx((0.5 + 1.0 + 1.0) / 3)


def test_attribution_right_facts_wrong_citation():
    b = attribution_breakdown(
        "It began on 24 April 2015 [10.1130/G39978.1].",
        valid_sources=SRC,
        relevant_sources=[SRC[0]],
        required_terms=["24 April 2015"],
    )
    assert b["citation_validity"] == 1.0
    assert b["citation_precision"] == 0.0 and b["citation_recall"] == 0.0


def test_attribution_uncited_answer_is_unsupported():
    scorer = make_attribution_scorer(
        valid_sources=SRC, relevant_sources=[SRC[0]], required_terms=["24 April 2015"]
    )
    assert scorer("It began on 24 April 2015.", None) == pytest.approx(1 / 3)


def test_attribution_forbidden_term_penalty():
    scorer = make_attribution_scorer(
        valid_sources=SRC, relevant_sources=[SRC[0]], required_terms=["0.45"], forbidden_terms=["0.54"]
    )
    assert scorer("Rates were 0.45 and 0.54 kPa/yr [10.1126/science.aah5563].", None) == pytest.approx(0.75)


def test_attribution_unanswerable_reference():
    b = attribution_breakdown(ABSTAIN_SENTINEL, valid_sources=SRC, relevant_sources=[])
    assert b["abstained"] and b["citation_recall"] == 1.0 and b["n_citations"] == 0


def test_attribution_numbered_mode():
    listed = ["SRC-A", "SRC-B", "SRC-C"]
    scorer = make_attribution_scorer(
        valid_sources=listed,
        relevant_sources=["SRC-B"],
        required_terms=["prest"],
        numbered=True,
        case_sensitive_terms=False,
    )
    b = scorer.breakdown("PREST measures seafloor pressure [2] and drifts [9].")
    assert b["fabricated"] == ["#9"]
    assert b["citation_validity"] == pytest.approx(0.5)
    assert b["citation_recall"] == 1.0 and b["citation_precision"] == pytest.approx(0.5)
    assert b["fact_coverage"] == 1.0  # case-insensitive, as Atlas matches entities


# --------------------------------------------------------------------------- #
# abstention: a proper scoring rule
# --------------------------------------------------------------------------- #
def test_abstention_unanswerable():
    scorer = make_abstention_scorer(answerable=False)
    assert scorer(ABSTAIN_SENTINEL, []) == 1.0
    assert scorer('["10.1126/science.aah5563"]', []) == 0.0
    assert scorer(f"{ABSTAIN_SENTINEL} although [10.1126/science.aah5563] is close", []) == 0.0


def test_abstention_answerable_declining_costs_the_point():
    scorer = make_abstention_scorer(answerable=True)
    gold = ["10.1126/science.aah5563"]
    assert scorer(ABSTAIN_SENTINEL, gold) == 0.0
    assert scorer('["10.1126/science.aah5563", "10.1130/G39978.1"]', gold) == 1.0
    assert scorer('["10.1130/G39978.1"]', gold) == 0.0
    assert scorer("It is [10.1126/SCIENCE.AAH5563].", gold) == 1.0  # DOIs are case-insensitive


def test_new_scorers_dispatch_from_spec():
    att = make_scorer_from_spec(
        {"name": "attribution", "config": {"valid_sources": ["A", "B"], "relevant_sources": ["B"], "numbered": True}}
    )
    assert att("claim [2]", None) == pytest.approx(1.0)
    ab = make_scorer_from_spec({"name": "abstention", "config": {"answerable": False}})
    assert ab(ABSTAIN_SENTINEL, None) == 1.0


# --------------------------------------------------------------------------- #
# shortlist with hard distractors
# --------------------------------------------------------------------------- #
POOL = terms_by_id(
    [
        ("gold", "bottom pressure recorder drift calibration Axial seamount"),
        ("near1", "bottom pressure recorder deployment Axial caldera"),
        ("near2", "pressure calibration drift ocean gauge"),
        ("far1", "hydrophone whale call detection"),
        ("far2", "seismometer clock timing offset"),
    ]
)


def test_shortlist_prefers_confusable_distractors_and_keeps_gold():
    picked = hard_shortlist(POOL["gold"], POOL, include=["gold"], k=3, seed="q1")
    assert set(picked) == {"gold", "near1", "near2"}


def test_shortlist_is_deterministic_and_gold_not_pinned_first():
    runs = {tuple(hard_shortlist(POOL["gold"], POOL, include=["gold"], k=3, seed=s)) for s in ("a", "a")}
    assert len(runs) == 1
    firsts = {hard_shortlist(POOL["gold"], POOL, include=["gold"], k=3, seed=f"s{i}")[0] for i in range(20)}
    assert len(firsts) > 1


def test_shortlist_rejects_bad_requests():
    with pytest.raises(ValueError):
        hard_shortlist(set(), POOL, include=["gold", "near1"], k=1, seed="x")
    with pytest.raises(KeyError):
        hard_shortlist(set(), POOL, include=["absent"], k=2, seed="x")


def test_content_terms_drop_stopwords_and_short_words():
    assert content_terms("We propose a new drift model for the BPR") == {"drift", "model"}
