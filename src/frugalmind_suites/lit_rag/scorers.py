"""Deterministic scorers for Family 1 (literature / RAG / translation).

Verifiable-core stance: each scorer compares against a reference with **no LLM
in the loop**, by decomposing "open-ended" literature tasks into their
verifiable pieces:

* ``retrieval_metrics`` — recall@k / MRR / nDCG@k / precision@k of a ranked
  document list against a gold relevant set (RAG retrieval axis, tier T0).
* ``term_preservation`` — fraction of must-preserve domain terms (station
  codes, magnitudes, phase names) that survive a translation, minus a penalty
  for forbidden/hallucinated terms (tier T0).
* ``citation_support`` — every ``[S#]`` citation in a grounded answer must
  resolve to a provided source (no fabricated citations), plus required facts
  present. The negative-case / hallucination guard for RAG answers (tier T0).

An LLM-judge faithfulness fallback (à la the STA/LTA report scorer) is
described in ``docs/lit_rag_scorers.md`` but intentionally kept out of this
reference so the leaderboard signal stays cheap and reproducible.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from typing import Any


def _parse_ranked_list(model_output: str) -> list[str]:
    """Pull a ranked list of ids out of a model response.

    Accepts a JSON array anywhere in the text; falls back to bracketed
    ``[S1] [S3]``-style tokens in order. Returns [] if nothing parses.
    """
    m = re.search(r"\[.*\]", model_output, re.DOTALL)
    if m:
        try:
            arr = json.loads(m.group(0))
            if isinstance(arr, list):
                return [str(x).strip() for x in arr]
        except json.JSONDecodeError:
            pass
    toks = re.findall(r"\[([A-Za-z0-9_\-]+)\]", model_output)
    return [t.strip() for t in toks]


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
        relevant = {str(x) for x in (gold or [])}
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
            dcg = sum(
                1.0 / math.log2(i + 1)
                for i, d in enumerate(top, start=1)
                if d in relevant
            )
            ideal = min(len(relevant), k)
            idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal + 1))
            return dcg / idcg if idcg else 0.0
        raise ValueError(f"unknown retrieval metric: {metric!r}")

    return scorer


def make_term_preservation_scorer(
    *,
    required_terms: list[str],
    forbidden_terms: list[str] | None = None,
    case_sensitive: bool = True,
) -> Callable[[str, Any], float]:
    """Fraction of must-preserve terms present, minus a hallucination penalty.

    Domain terms (station codes ``NC.JBGB``, magnitudes ``M4.2``, phase names
    ``Pn``) must survive verbatim through a translation. Each forbidden term
    present costs ``1/len(required_terms)`` (never below 0).
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


_CITE_RE = re.compile(r"\[([A-Za-z]+\d+)\]")


def make_citation_support_scorer(
    *,
    valid_sources: list[str],
    required_terms: list[str] | None = None,
    forbidden_terms: list[str] | None = None,
) -> Callable[[str, Any], float]:
    """Grounded-answer scorer: no fabricated citations + required facts present.

    * validity — fraction of ``[S#]`` citations that resolve to a provided
      source id. A single fabricated citation drags this down: the RAG
      hallucination guard.
    * coverage — fraction of ``required_terms`` present in the answer.

    Score = 0.5·validity + 0.5·coverage − forbidden-term penalty. An answer
    with no citations scores 0 on the validity half (unsupported by design).
    """
    valid = {str(s) for s in valid_sources}
    required = required_terms or []
    forbidden = forbidden_terms or []

    def scorer(model_output: str, gold: Any) -> float:
        cites = _CITE_RE.findall(model_output)
        if cites:
            validity = sum(1 for c in cites if c in valid) / len(cites)
        else:
            validity = 0.0

        if required:
            coverage = sum(1 for t in required if t in model_output) / len(required)
        else:
            coverage = 1.0

        score = 0.5 * validity + 0.5 * coverage
        penalty = 0.25 * sum(1 for t in forbidden if t in model_output)
        return max(0.0, min(1.0, score - penalty))

    return scorer


def make_scorer_from_spec(spec: dict[str, Any]) -> Callable[[str, Any], float]:
    """Reconstruct a Family-1 scorer callable from a JSON-serializable spec.

    Recognised names: ``retrieval_metrics``, ``term_preservation``,
    ``citation_support``, ``zero``.
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
    if name == "citation_support":
        return make_citation_support_scorer(
            valid_sources=config["valid_sources"],
            required_terms=config.get("required_terms"),
            forbidden_terms=config.get("forbidden_terms"),
        )
    if name == "zero":
        return lambda _out, _gold: 0.0
    raise ValueError(f"unknown scorer name: {name!r}")
