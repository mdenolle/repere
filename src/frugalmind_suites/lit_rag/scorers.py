"""Deterministic scorers for Family 1 (literature / RAG / translation).

Verifiable-core stance: each scorer compares against a reference with **no LLM
in the loop**, by decomposing "open-ended" literature tasks into their
verifiable pieces. The metric dimensions (see ``docs/lit_rag_scorers.md``):

* **Retrieval** — ``retrieval_metrics``: recall@k / precision@k / MRR / nDCG@k
  of a ranked document list against a gold relevant set (tier T0).
* **Attribution** — ``attribution``: are the cited ids real (validity), are
  they the right ones (citation precision / recall), and are the required
  facts present (fact coverage)? Sub-metrics ride along in the breakdown so a
  fabricated citation is never hidden inside a blended score (tier T0).
* **Abstention** — ``abstention``: a proper scoring rule over answerable and
  unanswerable queries. Declining an answerable query and answering an
  unanswerable one both cost the full point, so abstaining is never free and
  never punished when it is right (tier T0).
* **Term preservation** — ``term_preservation``: must-preserve domain terms
  (station codes, coordinates, magnitudes) survive a translation verbatim,
  minus a penalty for forbidden/hallucinated terms (tier T0).

Citations are recognised in two shapes: bracketed source keys (``[S2]``) and
DOIs (``[10.1126/science.aah5563]``, ``doi:10...``, ``https://doi.org/10...``),
so the same scorer grades a synthetic-key task and a real-corpus task.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from typing import Any

# Sentinel a model must emit, alone, to decline a query it cannot answer from
# the provided sources. Deterministic to detect; documented in every prompt.
ABSTAIN_SENTINEL = "NO_RELEVANT_PAPERS"

_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\]\)\"',;<>]+", re.IGNORECASE)
_KEY_RE = re.compile(r"\[([A-Za-z]+\d+)\]")


def _norm_id(s: str) -> str:
    return s.strip().rstrip(".").lower()


def extract_citations(text: str) -> list[str]:
    """All citation keys in ``text``, normalised, in order, de-duplicated.

    DOIs match anywhere (bracketed, ``doi:`` prefixed, or as a doi.org URL);
    short keys only match bracketed (``[S2]``). Normalisation is lower-case
    with a trailing period stripped, because DOIs are case-insensitive and
    models end sentences with them.
    """
    found: list[str] = []
    for m in _DOI_RE.findall(text):
        found.append(_norm_id(m))
    for m in _KEY_RE.findall(text):
        found.append(_norm_id(m))
    seen: set[str] = set()
    out: list[str] = []
    for c in found:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _parse_ranked_list(model_output: str) -> list[str]:
    """Pull a ranked list of ids out of a model response.

    Scans for the first *parseable* top-level JSON array via a balanced-bracket
    walk — a greedy ``[.*]`` would span from the array to a later bracketed
    token (e.g. a ``[S1]`` citation) and fail to parse, mis-scoring a correct
    answer. Falls back to citation extraction (DOIs or ``[S1]``-style keys)
    in order of appearance.
    """
    depth = 0
    start = None
    for i, ch in enumerate(model_output):
        if ch == "[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "]" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    arr = json.loads(model_output[start : i + 1])
                except json.JSONDecodeError:
                    start = None
                    continue
                if isinstance(arr, list):
                    return [_norm_id(str(x)) for x in arr]
                start = None
    return extract_citations(model_output)


def is_abstention(model_output: str) -> bool:
    """True when the response declines: the sentinel is present and nothing is cited."""
    return ABSTAIN_SENTINEL in model_output and not extract_citations(model_output)


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #
def make_retrieval_scorer(
    *,
    metric: str = "ndcg_at_k",
    k: int = 10,
) -> Callable[[str, Any], float]:
    """Score a ranked document list against a gold relevant set.

    ``gold`` (runtime arg) is the list of relevant document ids. Metrics:
    ``recall_at_k``, ``precision_at_k``, ``mrr``, ``ndcg_at_k``.
    """

    def scorer(model_output: str, gold: Any) -> float:
        ranked = _parse_ranked_list(model_output)
        relevant = {_norm_id(str(x)) for x in (gold or [])}
        if not relevant:
            return 0.0
        top = ranked[:k]

        if metric == "recall_at_k":
            return len([d for d in top if d in relevant]) / len(relevant)
        if metric == "precision_at_k":
            return len([d for d in top if d in relevant]) / k if k else 0.0
        if metric == "mrr":
            for i, d in enumerate(ranked, start=1):
                if d in relevant:
                    return 1.0 / i
            return 0.0
        if metric == "ndcg_at_k":
            dcg = sum(1.0 / math.log2(i + 1) for i, d in enumerate(top, start=1) if d in relevant)
            ideal = min(len(relevant), k)
            idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal + 1))
            return dcg / idcg if idcg else 0.0
        raise ValueError(f"unknown retrieval metric: {metric!r}")

    return scorer


# --------------------------------------------------------------------------- #
# Term preservation (translation)
# --------------------------------------------------------------------------- #
def make_term_preservation_scorer(
    *,
    required_terms: list[str],
    forbidden_terms: list[str] | None = None,
    case_sensitive: bool = True,
) -> Callable[[str, Any], float]:
    """Fraction of must-preserve terms present, minus a hallucination penalty.

    Domain terms (station codes ``HYS14``, coordinates, magnitudes) must
    survive verbatim through a translation. Each forbidden term present costs
    ``1/len(required_terms)`` (never below 0).
    """
    forbidden = forbidden_terms or []

    def _present(term: str, text: str) -> bool:
        if case_sensitive:
            return term in text
        return term.lower() in text.lower()

    def scorer(model_output: str, gold: Any) -> float:
        if not required_terms:
            return 0.0
        hits = sum(1 for t in required_terms if _present(t, model_output))
        base = hits / len(required_terms)
        penalty = sum(1 for t in forbidden if _present(t, model_output))
        penalty_frac = penalty / len(required_terms)
        return max(0.0, min(1.0, base - penalty_frac))

    return scorer


# --------------------------------------------------------------------------- #
# Attribution (grounded answers)
# --------------------------------------------------------------------------- #
def attribution_breakdown(
    model_output: str,
    *,
    valid_sources: list[str],
    relevant_sources: list[str] | None = None,
    required_terms: list[str] | None = None,
    forbidden_terms: list[str] | None = None,
) -> dict[str, Any]:
    """Per-dimension attribution metrics for one grounded answer.

    * ``citation_validity`` — cited ids that resolve to a provided source.
    * ``citation_precision`` — cited ids that are in the gold relevant set.
    * ``citation_recall`` — gold relevant ids that were cited.
    * ``fabricated`` — cited ids that resolve to nothing (the hallucinated
      reference; reported as a list so it is auditable, not just a rate).
    * ``fact_coverage`` — fraction of ``required_terms`` present verbatim.
    * ``n_forbidden`` — forbidden terms present (a wrong number, a renamed
      site).
    * ``abstained`` — the answer declined instead of answering.

    Validity and precision are 0 when nothing is cited: an uncited answer is
    unsupported by construction. Recall is 0 then too, unless nothing was
    relevant to cite.
    """
    valid = {_norm_id(s) for s in valid_sources}
    relevant = {_norm_id(s) for s in (relevant_sources or [])}
    required = required_terms or []
    forbidden = forbidden_terms or []

    cites = extract_citations(model_output)
    n = len(cites)
    fabricated = [c for c in cites if c not in valid]
    validity = (n - len(fabricated)) / n if n else 0.0
    precision = sum(1 for c in cites if c in relevant) / n if n else 0.0
    if relevant:
        recall = sum(1 for r in relevant if r in cites) / len(relevant)
    else:
        recall = 1.0 if not cites else 0.0
    coverage = sum(1 for t in required if t in model_output) / len(required) if required else 1.0
    n_forbidden = sum(1 for t in forbidden if t in model_output)
    return {
        "n_citations": n,
        "citation_validity": validity,
        "citation_precision": precision,
        "citation_recall": recall,
        "fabricated": fabricated,
        "fact_coverage": coverage,
        "n_forbidden": n_forbidden,
        "abstained": is_abstention(model_output),
    }


def make_attribution_scorer(
    *,
    valid_sources: list[str],
    relevant_sources: list[str] | None = None,
    required_terms: list[str] | None = None,
    forbidden_terms: list[str] | None = None,
    weights: dict[str, float] | None = None,
) -> Callable[[str, Any], float]:
    """Scalar attribution score with an auditable ``.breakdown`` attribute.

    ``score = w_validity·validity + w_recall·recall + w_coverage·coverage
    − 0.25·n_forbidden``, clipped to [0, 1]. Defaults weight the three evenly.
    A single fabricated citation lowers validity; a missed key paper lowers
    recall; a missing number lowers coverage. Precision is reported in the
    breakdown but not blended, so citing an extra provided-but-irrelevant
    source is visible without being punished twice.
    """
    w = {"validity": 1 / 3, "recall": 1 / 3, "coverage": 1 / 3}
    if weights:
        w.update(weights)

    def breakdown(model_output: str, gold: Any = None) -> dict[str, Any]:
        return attribution_breakdown(
            model_output,
            valid_sources=valid_sources,
            relevant_sources=relevant_sources,
            required_terms=required_terms,
            forbidden_terms=forbidden_terms,
        )

    def scorer(model_output: str, gold: Any) -> float:
        b = breakdown(model_output, gold)
        score = (
            w["validity"] * b["citation_validity"]
            + w["recall"] * b["citation_recall"]
            + w["coverage"] * b["fact_coverage"]
            - 0.25 * b["n_forbidden"]
        )
        return max(0.0, min(1.0, score))

    scorer.breakdown = breakdown  # type: ignore[attr-defined]
    return scorer


def make_citation_support_scorer(
    *,
    valid_sources: list[str],
    required_terms: list[str] | None = None,
    forbidden_terms: list[str] | None = None,
) -> Callable[[str, Any], float]:
    """Legacy grounded-answer scorer: 0.5·validity + 0.5·coverage − penalty.

    Kept for rows that still carry ``scorer: citation_support``; new items
    should use ``attribution``, which also reports citation recall/precision.
    """
    return make_attribution_scorer(
        valid_sources=valid_sources,
        relevant_sources=None,
        required_terms=required_terms,
        forbidden_terms=forbidden_terms,
        weights={"validity": 0.5, "recall": 0.0, "coverage": 0.5},
    )


# --------------------------------------------------------------------------- #
# Abstention (proper scoring rule)
# --------------------------------------------------------------------------- #
def make_abstention_scorer(
    *,
    answerable: bool,
) -> Callable[[str, Any], float]:
    """Score a query that may or may not be answerable from the corpus.

    * ``answerable=False`` (nothing relevant exists): 1.0 for a clean
      abstention (sentinel, no citations), 0.0 otherwise. Any citation is a
      confabulated relevance claim.
    * ``answerable=True`` (``gold`` = relevant ids): 0.0 for an abstention;
      otherwise the fraction of gold ids cited/ranked (recall over the
      full response). Declining is never free.

    The rule is proper: a model maximises expected score only by abstaining
    exactly when it has no relevant evidence.
    """

    def scorer(model_output: str, gold: Any) -> float:
        abstained = is_abstention(model_output)
        if not answerable:
            return 1.0 if abstained else 0.0
        if abstained:
            return 0.0
        relevant = {_norm_id(str(x)) for x in (gold or [])}
        if not relevant:
            return 0.0
        cited = set(_parse_ranked_list(model_output))
        return sum(1 for r in relevant if r in cited) / len(relevant)

    return scorer


# --------------------------------------------------------------------------- #
# Spec dispatch
# --------------------------------------------------------------------------- #
def make_scorer_from_spec(spec: dict[str, Any]) -> Callable[[str, Any], float]:
    """Reconstruct a Family-1 scorer callable from a JSON-serializable spec.

    Recognised names: ``retrieval_metrics``, ``term_preservation``,
    ``attribution``, ``citation_support`` (legacy), ``abstention``, ``zero``.
    """
    name = spec["name"]
    config = dict(spec.get("config", {}))
    if name == "retrieval_metrics":
        return make_retrieval_scorer(
            metric=config.get("metric", "ndcg_at_k"),
            k=config.get("k", 10),
        )
    if name == "term_preservation":
        return make_term_preservation_scorer(
            required_terms=config["required_terms"],
            forbidden_terms=config.get("forbidden_terms"),
            case_sensitive=config.get("case_sensitive", True),
        )
    if name == "attribution":
        return make_attribution_scorer(
            valid_sources=config["valid_sources"],
            relevant_sources=config.get("relevant_sources"),
            required_terms=config.get("required_terms"),
            forbidden_terms=config.get("forbidden_terms"),
            weights=config.get("weights"),
        )
    if name == "citation_support":
        return make_citation_support_scorer(
            valid_sources=config["valid_sources"],
            required_terms=config.get("required_terms"),
            forbidden_terms=config.get("forbidden_terms"),
        )
    if name == "abstention":
        return make_abstention_scorer(answerable=bool(config.get("answerable", True)))
    if name == "zero":
        return lambda _out, _gold: 0.0
    raise ValueError(f"unknown scorer name: {name!r}")


__all__ = [
    "ABSTAIN_SENTINEL",
    "attribution_breakdown",
    "extract_citations",
    "is_abstention",
    "make_abstention_scorer",
    "make_attribution_scorer",
    "make_citation_support_scorer",
    "make_retrieval_scorer",
    "make_scorer_from_spec",
    "make_term_preservation_scorer",
]
