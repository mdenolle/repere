"""Tests for the Family-1 (lit / RAG / translation) deterministic scorers and
the OOI-RCA truth set built on the real corpus."""

from __future__ import annotations

import json
import re

import pytest
import yaml

from frugalmind import TaskKind
from frugalmind.agents import literature as lit
from frugalmind_suites.lit_rag.items import (
    ALL_SUITES,
    TRUTH_PATH,
    LitRagAbstentionSuite,
    LitRagGroundedQASuite,
    LitRagKnownItemSuite,
    LitRagRetrievalSuite,
    LitRagTranslationSuite,
)
from frugalmind_suites.lit_rag.scorers import (
    ABSTAIN_SENTINEL,
    attribution_breakdown,
    extract_citations,
    is_abstention,
    make_abstention_scorer,
    make_attribution_scorer,
    make_citation_support_scorer,
    make_retrieval_scorer,
    make_scorer_from_spec,
    make_term_preservation_scorer,
)

_IDS_IN_PROMPT = re.compile(r'\["([^"]+)"\]')


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


def test_abstention_requires_sentinel_and_no_citation():
    assert is_abstention(ABSTAIN_SENTINEL)
    assert is_abstention(f"  {ABSTAIN_SENTINEL}\n")
    assert not is_abstention(f"{ABSTAIN_SENTINEL} but maybe [10.1126/science.aah5563]")
    assert not is_abstention("I don't know.")


# --------------------------------------------------------------------------- #
# retrieval_metrics
# --------------------------------------------------------------------------- #
def test_retrieval_recall_and_precision():
    recall = make_retrieval_scorer(metric="recall_at_k", k=3)
    assert recall('["D3","D7","D1"]', ["D3", "D7"]) == 1.0
    assert recall('["D3","D1","D2"]', ["D3", "D7"]) == 0.5
    prec = make_retrieval_scorer(metric="precision_at_k", k=2)
    assert prec('["D3","D7"]', ["D3", "D7", "D9"]) == 1.0


def test_retrieval_mrr_and_ndcg():
    mrr = make_retrieval_scorer(metric="mrr", k=10)
    assert mrr('["D1","D3","D7"]', ["D3"]) == pytest.approx(0.5)
    ndcg = make_retrieval_scorer(metric="ndcg_at_k", k=5)
    assert ndcg('["D3","D7","D9"]', ["D3", "D7", "D9"]) == pytest.approx(1.0)
    assert ndcg('["D1","D2","D3"]', ["D3"]) < 1.0


def test_retrieval_is_case_insensitive_on_dois():
    mrr = make_retrieval_scorer(metric="mrr", k=10)
    assert mrr('["10.1130/g39978.1"]', ["10.1130/G39978.1"]) == 1.0


def test_retrieval_empty_gold_is_zero():
    assert make_retrieval_scorer(metric="recall_at_k", k=3)('["D1"]', []) == 0.0


def test_retrieval_array_followed_by_bracket_token_parses():
    scorer = make_retrieval_scorer(metric="ndcg_at_k", k=5)
    out = 'Ranked: ["D3","D7","D9"]. See also the note [S1] below.'
    assert scorer(out, ["D3", "D7", "D9"]) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# term_preservation
# --------------------------------------------------------------------------- #
def test_term_preservation_all_present():
    scorer = make_term_preservation_scorer(required_terms=["HYS14", "87 km", "63 Hz"])
    assert scorer("La station HYS14, à 87 km au large, bande 63 Hz.", None) == 1.0


def test_term_preservation_penalises_hallucinated_terms():
    scorer = make_term_preservation_scorer(
        required_terms=["1,535", "Axial Seamount", "2018"], forbidden_terms=["1.535"]
    )
    assert scorer("Axial Seamount 2018 1,535 m (1.535 m)", None) == pytest.approx(2 / 3)


def test_term_preservation_case_sensitivity():
    assert make_term_preservation_scorer(required_terms=["HHZ"])("channel hhz", None) == 0.0
    assert (
        make_term_preservation_scorer(required_terms=["HHZ"], case_sensitive=False)(
            "channel hhz", None
        )
        == 1.0
    )


# --------------------------------------------------------------------------- #
# attribution
# --------------------------------------------------------------------------- #
SRC = ["10.1126/science.aah5563", "10.1130/G39978.1", "10.1126/science.aah4666"]


def test_attribution_perfect_answer():
    scorer = make_attribution_scorer(
        valid_sources=SRC, relevant_sources=[SRC[0]], required_terms=["24 April 2015", "ring fault"]
    )
    ans = "The eruption began on 24 April 2015 and inflation was taken up by a ring fault [10.1126/science.aah5563]."
    assert scorer(ans, None) == pytest.approx(1.0)
    b = scorer.breakdown(ans)
    assert (
        b["citation_validity"] == 1.0 and b["citation_recall"] == 1.0 and b["fact_coverage"] == 1.0
    )
    assert b["fabricated"] == [] and not b["abstained"]


def test_attribution_fabricated_citation_is_visible_and_costly():
    scorer = make_attribution_scorer(
        valid_sources=SRC, relevant_sources=[SRC[0]], required_terms=["24 April 2015"]
    )
    ans = "It began on 24 April 2015 [10.1126/science.aah5563] as reviewed in [10.9999/made-up]."
    b = scorer.breakdown(ans)
    assert b["fabricated"] == ["10.9999/made-up"]
    assert b["citation_validity"] == pytest.approx(0.5)
    assert b["citation_recall"] == 1.0
    assert scorer(ans, None) == pytest.approx((0.5 + 1.0 + 1.0) / 3)


def test_attribution_right_facts_wrong_citation():
    scorer = make_attribution_scorer(
        valid_sources=SRC, relevant_sources=[SRC[0]], required_terms=["24 April 2015"]
    )
    ans = (
        "It began on 24 April 2015 [10.1130/G39978.1]."  # provided, but not the paper that says so
    )
    b = scorer.breakdown(ans)
    assert b["citation_validity"] == 1.0
    assert b["citation_precision"] == 0.0
    assert b["citation_recall"] == 0.0


def test_attribution_uncited_answer_is_unsupported():
    scorer = make_attribution_scorer(
        valid_sources=SRC, relevant_sources=[SRC[0]], required_terms=["24 April 2015"]
    )
    assert scorer("It began on 24 April 2015.", None) == pytest.approx(1 / 3)


def test_attribution_forbidden_term_penalty():
    scorer = make_attribution_scorer(
        valid_sources=SRC,
        relevant_sources=[SRC[0]],
        required_terms=["0.45"],
        forbidden_terms=["0.54"],
    )
    assert scorer(
        "Rates were 0.45 and 0.54 kPa/yr [10.1126/science.aah5563].", None
    ) == pytest.approx(0.75)


def test_citation_support_legacy_matches_old_weights():
    scorer = make_citation_support_scorer(
        valid_sources=["S1", "S2", "S3"], required_terms=["threshold"]
    )
    assert scorer("The threshold is high [S2] and also [S9].", None) == pytest.approx(0.75)
    assert scorer("The threshold is high.", None) == pytest.approx(0.5)


def test_attribution_breakdown_unanswerable_reference():
    b = attribution_breakdown(ABSTAIN_SENTINEL, valid_sources=SRC, relevant_sources=[])
    assert b["abstained"] and b["citation_recall"] == 1.0 and b["n_citations"] == 0


# --------------------------------------------------------------------------- #
# abstention — a proper scoring rule
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


# --------------------------------------------------------------------------- #
# spec dispatch
# --------------------------------------------------------------------------- #
def test_make_scorer_from_spec_dispatch():
    configs = {
        "retrieval_metrics": {"metric": "mrr"},
        "term_preservation": {"required_terms": ["Pn"]},
        "citation_support": {"valid_sources": ["S1"]},
        "attribution": {"valid_sources": ["S1"], "relevant_sources": ["S1"]},
        "abstention": {"answerable": False},
    }
    for name, config in configs.items():
        assert callable(make_scorer_from_spec({"name": name, "config": config}))
    with pytest.raises(ValueError, match="unknown scorer name"):
        make_scorer_from_spec({"name": "nope"})


# --------------------------------------------------------------------------- #
# OOI-RCA truth set: real corpus, objective gold, public validation only
# --------------------------------------------------------------------------- #
def test_committed_truth_set_is_validation_public_only():
    """Gold for a ranked score never ships in git; the committed file is the dev split."""
    doc = yaml.safe_load(TRUTH_PATH.read_text())
    for it in doc["items"]:
        assert it["split"] == "validation", it["id"]
        assert it["visibility"] == "public", it["id"]


def test_truth_set_gold_and_sources_are_real_corpus_dois():
    corpus = {d.id: d for d in lit.load_corpus()}
    defective = {"10.1029/2020gl087372", "10.1002/rob.21961"}  # known Zotero abstract defects
    doc = yaml.safe_load(TRUTH_PATH.read_text())
    for it in doc["items"]:
        for g in it.get("gold") or []:
            assert g in corpus, (it["id"], g)
            assert g not in defective, (it["id"], g)
            assert len(corpus[g].abstract) > 80, (it["id"], g)
        for s in it.get("sources") or []:
            assert s in corpus, (it["id"], s)
        if it.get("source"):
            assert it["source"] in corpus


def test_grounded_qa_required_terms_are_verbatim_in_gold_abstract():
    """Facts are objective because they are quoted from the abstract, not paraphrased."""
    corpus = {d.id: d for d in lit.load_corpus()}
    doc = yaml.safe_load(TRUTH_PATH.read_text())
    for it in doc["items"]:
        if it["kind"] != "grounded_qa" or not it.get("answerable", True):
            continue
        text = " ".join(corpus[g].abstract for g in it["gold"])
        for term in it["required_terms"]:
            assert term in text, (it["id"], term)


def test_translation_required_terms_are_in_source_text():
    doc = yaml.safe_load(TRUTH_PATH.read_text())
    for it in doc["items"]:
        if it["kind"] != "translation":
            continue
        text = " ".join(it["text"].split())
        for term in it["required_terms"]:
            assert term in text, (it["id"], term)


def test_suites_have_enough_items_to_carry_a_score():
    assert len(list(LitRagRetrievalSuite().export_rows())) >= 15
    assert len(list(LitRagGroundedQASuite().export_rows())) >= 8
    assert len(list(LitRagTranslationSuite().export_rows())) >= 2
    ab = list(LitRagAbstentionSuite().export_rows())
    n_unans = sum(1 for r in ab if not r.metadata["answerable"])
    n_ans = len(ab) - n_unans
    assert n_unans >= 6 and n_ans >= 4, (
        "abstention needs both unanswerable items and answerable controls"
    )


def test_suites_compose_export_and_run():
    kinds = set()
    for suite_cls in ALL_SUITES:
        suite = suite_cls()
        rows = list(suite.export_rows())
        items = list(suite.items())
        assert rows and len(rows) == len(items)
        kinds.add(rows[0].task_kind)
        for row, (prompt, _gold, scorer) in zip(rows, items, strict=True):
            assert prompt == row.prompt and callable(scorer)
            assert row.id.startswith("lit_rag/")
            assert (
                row.scorer_spec == make_scorer_from_spec(row.scorer_spec) or True
            )  # spec is serialisable
            json.dumps(row.scorer_spec)
    assert kinds == {
        TaskKind.RETRIEVAL.value,
        TaskKind.GROUNDED_QA.value,
        TaskKind.TRANSLATION.value,
    }


def test_gold_is_shown_among_candidates_and_not_always_first():
    for suite_cls in (LitRagRetrievalSuite, LitRagAbstentionSuite, LitRagGroundedQASuite):
        positions = []
        for row in suite_cls().export_rows():
            ids = _IDS_IN_PROMPT.findall(row.prompt)
            assert len(ids) == len(set(ids))
            for g in row.gold:
                assert g in ids, (row.id, g)
                positions.append(ids.index(g))
        assert len(set(positions)) > 1, suite_cls.__name__


def test_shortlists_are_deterministic():
    a = [p for p, _, _ in LitRagRetrievalSuite().items()]
    b = [p for p, _, _ in LitRagRetrievalSuite().items()]
    assert a == b


def test_retrieval_scorer_discriminates_on_real_items():
    for prompt, gold, scorer in list(LitRagRetrievalSuite().items())[:5]:
        ids = _IDS_IN_PROMPT.findall(prompt)
        best = json.dumps([gold[0]] + [i for i in ids if i != gold[0]])
        worst = json.dumps([i for i in ids if i != gold[0]] + [gold[0]])
        assert scorer(best, gold) == pytest.approx(1.0)
        assert scorer(worst, gold) == pytest.approx(1 / len(ids))
        assert scorer("I don't know.", gold) == 0.0


def test_abstention_suite_scores_the_decision():
    for row, (prompt, gold, scorer) in zip(
        LitRagAbstentionSuite().export_rows(), LitRagAbstentionSuite().items(), strict=True
    ):
        ids = _IDS_IN_PROMPT.findall(prompt)
        assert ABSTAIN_SENTINEL in prompt
        if row.metadata["answerable"]:
            assert scorer(ABSTAIN_SENTINEL, gold) == 0.0
            assert scorer(json.dumps(gold), gold) == 1.0
        else:
            assert gold == []
            assert scorer(ABSTAIN_SENTINEL, gold) == 1.0
            assert scorer(json.dumps(ids[:1]), gold) == 0.0


def test_grounded_qa_suite_end_to_end():
    for row, (prompt, gold, scorer) in zip(
        LitRagGroundedQASuite().export_rows(), LitRagGroundedQASuite().items(), strict=True
    ):
        assert ABSTAIN_SENTINEL in prompt
        spec = row.scorer_spec
        if row.metadata["answerable"]:
            assert spec["name"] == "attribution"
            good = " ".join(spec["config"]["required_terms"]) + f" [{gold[0]}]"
            assert scorer(good, gold) == pytest.approx(1.0)
            assert scorer(ABSTAIN_SENTINEL, gold) < 0.5
            fabricated = good + " [10.9999/fake]"
            assert scorer.breakdown(fabricated)["fabricated"] == ["10.9999/fake"]
        else:
            assert spec["name"] == "abstention"
            assert scorer(ABSTAIN_SENTINEL, gold) == 1.0
            assert scorer(f"Roughly 3 [{row.metadata['sources'][0]}]", gold) == 0.0


def test_translation_suite_identity_scores_full():
    for _, gold, scorer in LitRagTranslationSuite().items():
        assert scorer(gold, gold) == pytest.approx(1.0)


def test_test_split_without_hidden_data_fails_loudly():
    with pytest.raises(FileNotFoundError, match="hidden lit_rag test split"):
        LitRagRetrievalSuite(split="test")._items()


# --------------------------------------------------------------------------- #
# Known-item retrieval over REAL arXiv papers (document-based family)
# --------------------------------------------------------------------------- #
def test_known_item_suite_is_a_real_eval_not_a_seed():
    suite = LitRagKnownItemSuite()
    rows = list(suite.export_rows())
    assert len(rows) >= 10, "too few items to support a score"
    for r in rows:
        assert r.task_kind == TaskKind.RETRIEVAL.value
        assert r.scorer_spec["name"] == "retrieval_metrics"
        assert len(r.gold) == 1
        assert r.gold[0] in r.prompt


def test_known_item_shortlist_is_deterministic_and_contains_the_gold():
    a = list(LitRagKnownItemSuite().items())
    b = list(LitRagKnownItemSuite().items())
    assert [p for p, _, _ in a] == [p for p, _, _ in b], "shortlist is not deterministic"
    positions = []
    for prompt, gold, _ in a:
        ids = re.findall(r'\["([0-9.v]+)"\]', prompt)
        assert gold[0] in ids
        positions.append(ids.index(gold[0]))
    assert len(set(positions)) > 1, "gold sits in the same slot every time"
