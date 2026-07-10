"""Tests for the Family-1 (lit / RAG / translation) deterministic scorers."""

from __future__ import annotations

import pytest

from frugalmind import TaskKind
from frugalmind_suites.lit_rag.items import (
    ALL_SUITES,
    LitRagGroundedQASuite,
    LitRagRetrievalSuite,
    LitRagTranslationSuite,
)
from frugalmind_suites.lit_rag.scorers import (
    make_citation_support_scorer,
    make_retrieval_scorer,
    make_scorer_from_spec,
    make_term_preservation_scorer,
)


# --------------------------------------------------------------------------- #
# retrieval_metrics
# --------------------------------------------------------------------------- #
def test_retrieval_recall_and_precision():
    recall = make_retrieval_scorer(metric="recall_at_k", k=3)
    # 2 of 2 relevant in top-3
    assert recall('["D3","D7","D1"]', ["D3", "D7"]) == 1.0
    # 1 of 2 relevant in top-3
    assert recall('["D3","D1","D2"]', ["D3", "D7"]) == 0.5

    prec = make_retrieval_scorer(metric="precision_at_k", k=2)
    assert prec('["D3","D7"]', ["D3", "D7", "D9"]) == 1.0


def test_retrieval_mrr_and_ndcg():
    mrr = make_retrieval_scorer(metric="mrr", k=10)
    assert mrr('["D1","D3","D7"]', ["D3"]) == pytest.approx(0.5)  # first rel at rank 2

    ndcg = make_retrieval_scorer(metric="ndcg_at_k", k=5)
    # perfect ranking -> 1.0
    assert ndcg('["D3","D7","D9"]', ["D3", "D7", "D9"]) == pytest.approx(1.0)
    # a relevant doc pushed down scores < 1
    assert ndcg('["D1","D2","D3"]', ["D3"]) < 1.0


def test_retrieval_empty_gold_is_zero():
    scorer = make_retrieval_scorer(metric="recall_at_k", k=3)
    assert scorer('["D1"]', []) == 0.0


def test_retrieval_array_followed_by_bracket_token_parses():
    # Regression: a greedy [.*] would span the array into a trailing [S1]
    # citation and fail to parse, falling back to token matching. The
    # balanced-bracket scan must still recover the real ranked array.
    scorer = make_retrieval_scorer(metric="ndcg_at_k", k=5)
    out = 'Ranked: ["D3","D7","D9"]. See also the note [S1] below.'
    assert scorer(out, ["D3", "D7", "D9"]) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# term_preservation
# --------------------------------------------------------------------------- #
def test_term_preservation_all_present():
    scorer = make_term_preservation_scorer(required_terms=["NC.JBGB", "M4.2", "Pn"])
    text = "La estación NC.JBGB registró un evento M4.2 con llegada Pn."
    assert scorer(text, None) == 1.0


def test_term_preservation_penalises_hallucinated_terms():
    scorer = make_term_preservation_scorer(
        required_terms=["NC.JBGB", "M4.2", "Pn"],
        forbidden_terms=["M4.0"],
    )
    # all present but a rounded magnitude also appears -> -1/3
    text = "NC.JBGB M4.2 Pn ... (aprox M4.0)"
    assert scorer(text, None) == pytest.approx(2 / 3)


def test_term_preservation_case_sensitivity():
    strict = make_term_preservation_scorer(required_terms=["HHZ"])
    assert strict("channel hhz", None) == 0.0
    loose = make_term_preservation_scorer(required_terms=["HHZ"], case_sensitive=False)
    assert loose("channel hhz", None) == 1.0


# --------------------------------------------------------------------------- #
# citation_support
# --------------------------------------------------------------------------- #
def test_citation_support_valid_and_covered():
    scorer = make_citation_support_scorer(
        valid_sources=["S1", "S2", "S3"], required_terms=["3.5", "threshold"]
    )
    ans = "The recommended threshold is 3.5 [S2]."
    assert scorer(ans, None) == pytest.approx(1.0)


def test_citation_support_fabricated_citation_drags_validity():
    scorer = make_citation_support_scorer(
        valid_sources=["S1", "S2", "S3"], required_terms=["threshold"]
    )
    # one of two citations is fabricated -> validity 0.5, coverage 1.0 -> 0.75
    ans = "The threshold is high [S2] and also [S9]."
    assert scorer(ans, None) == pytest.approx(0.75)


def test_citation_support_no_citations_is_half_at_most():
    scorer = make_citation_support_scorer(
        valid_sources=["S1"], required_terms=["threshold"]
    )
    ans = "The threshold is high."  # covered but uncited
    assert scorer(ans, None) == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# spec dispatch + suite integration
# --------------------------------------------------------------------------- #
def test_make_scorer_from_spec_dispatch():
    for name in ("retrieval_metrics", "term_preservation", "citation_support"):
        config = {
            "retrieval_metrics": {"metric": "mrr"},
            "term_preservation": {"required_terms": ["Pn"]},
            "citation_support": {"valid_sources": ["S1"]},
        }[name]
        assert callable(make_scorer_from_spec({"name": name, "config": config}))
    with pytest.raises(ValueError, match="unknown scorer name"):
        make_scorer_from_spec({"name": "nope"})


def test_suites_compose_export_and_run():
    kinds = set()
    for suite_cls in ALL_SUITES:
        suite = suite_cls(split="validation")
        rows = list(suite.export_rows())
        assert len(rows) == 1  # one seed task per kind
        kinds.add(rows[0].task_kind)
        # items() are runnable triples
        prompt, gold, scorer = next(iter(suite.items()))
        assert callable(scorer)
        assert isinstance(prompt, str) and prompt
    assert kinds == {
        TaskKind.RETRIEVAL.value,
        TaskKind.TRANSLATION.value,
        TaskKind.GROUNDED_QA.value,
    }


def test_end_to_end_retrieval_suite_scores_perfectly():
    suite = LitRagRetrievalSuite(split="validation")
    _, gold, scorer = next(iter(suite.items()))
    # gold relevant set ranked first -> ndcg 1.0
    ranked = "[" + ",".join(f'"{d}"' for d in gold) + "]"
    assert scorer(ranked, gold) == pytest.approx(1.0)


def test_translation_and_grounded_suites_exist():
    assert LitRagTranslationSuite().task_kind == TaskKind.TRANSLATION
    assert LitRagGroundedQASuite().task_kind == TaskKind.GROUNDED_QA
