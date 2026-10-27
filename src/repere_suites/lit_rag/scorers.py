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
* ``attribution`` — the full citation picture for a grounded answer: validity
  (cited ids resolve to a provided source), precision and recall against the
  gold relevant sources, the list of fabricated ids, and fact coverage. The
  sub-metrics ride along in ``.breakdown`` so a fabricated citation is never
  hidden inside a blended score (tier T0).
* ``abstention`` — a proper scoring rule over answerable and unanswerable
  queries: declining an answerable one and answering an unanswerable one both
  cost the full point (tier T0).

Citations are read in three shapes: DOIs (bracketed, ``doi:`` or a doi.org
URL), bracketed keys (``[S2]``), and, when the scorer is given the numbered
source list the model saw, numbered references (``[3]``, ``[2-4]``,
``[1, 5]``) as RCA Atlas answers write them. A number outside the list is a
fabricated citation.

``attribution`` and ``abstention`` were written on the archived branch
``archive/lit-rag-ooi-rca-2026-09`` (2026-09-15) and ported here for the
RCA Atlas answer data (ROADMAP P3.7); numbered citations are new.

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

    Scans for the first *parseable* top-level JSON array via a balanced-bracket
    walk — a greedy ``[.*]`` would span from the array to a later bracketed
    token (e.g. a ``[S1]`` citation) and fail to parse, mis-scoring a correct
    answer. Falls back to bracketed ``[S1] [S3]``-style tokens in order.
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
                    return [str(x).strip() for x in arr]
                start = None
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


# --------------------------------------------------------------------------- #
# Citation extraction, attribution and abstention
# --------------------------------------------------------------------------- #

# Sentinel a model must emit, alone, to decline a query it cannot answer from
# the provided sources. Deterministic to detect; every prompt must state it.
ABSTAIN_SENTINEL = "NO_RELEVANT_PAPERS"

_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\]\)\"',;<>]+", re.IGNORECASE)
_KEY_RE = re.compile(r"\[([A-Za-z]+\d+)\]")
_NUM_RE = re.compile(r"\[(\d+(?:\s*[-–,]\s*\d+)*)\]")


def _norm_id(s: str) -> str:
    return str(s).strip().rstrip(".").lower()


def _numbered_refs(text: str) -> list[int]:
    """``[3]``, ``[2-4]``, ``[1, 5]`` -> [3, 2, 3, 4, 1, 5]: the RCA Atlas convention."""
    out: list[int] = []
    for m in _NUM_RE.finditer(text):
        for part in re.split(r"\s*,\s*", m[1]):
            if re.search(r"[-–]", part):
                a, b = (int(x) for x in re.split(r"\s*[-–]\s*", part))
                out.extend(range(a, b + 1) if a <= b else [a, b])
            else:
                out.append(int(part))
    return out


def extract_citations(text: str, *, numbered_sources: list[str] | None = None) -> list[str]:
    """All citation ids in ``text``, normalised, in order of first appearance.

    DOIs match anywhere; short keys only bracketed (``[S2]``). With
    ``numbered_sources`` (the ids of the sources the model was shown, in the
    order it saw them), ``[n]`` resolves to ``numbered_sources[n-1]`` and an
    out-of-range ``n`` becomes ``"#n"``, which no valid source matches.
    Without it, bare numbers are ignored: ``[12]`` could be anything.
    Normalisation is lower-case with a trailing period stripped, because DOIs
    are case-insensitive and models end sentences with them.
    """
    found = [_norm_id(m) for m in _DOI_RE.findall(text)]
    found += [_norm_id(m) for m in _KEY_RE.findall(text)]
    if numbered_sources is not None:
        for n in _numbered_refs(text):
            ok = 1 <= n <= len(numbered_sources)
            found.append(_norm_id(numbered_sources[n - 1]) if ok else f"#{n}")
    seen: set[str] = set()
    return [c for c in found if not (c in seen or seen.add(c))]


def is_abstention(model_output: str, *, numbered_sources: list[str] | None = None) -> bool:
    """True when the response declines: the sentinel is present and nothing is cited."""
    return ABSTAIN_SENTINEL in model_output and not extract_citations(
        model_output, numbered_sources=numbered_sources
    )


def attribution_breakdown(
    model_output: str,
    *,
    valid_sources: list[str],
    relevant_sources: list[str] | None = None,
    required_terms: list[str] | None = None,
    forbidden_terms: list[str] | None = None,
    numbered: bool = False,
    case_sensitive_terms: bool = True,
) -> dict[str, Any]:
    """Per-dimension attribution metrics for one grounded answer.

    * ``citation_validity`` — cited ids that resolve to a provided source.
    * ``citation_precision`` — cited ids that are in the gold relevant set.
    * ``citation_recall`` — gold relevant ids that were cited.
    * ``fabricated`` — cited ids that resolve to nothing, as a list so the
      invented reference is auditable, not just a rate.
    * ``fact_coverage`` — fraction of ``required_terms`` present verbatim.
    * ``n_forbidden`` — forbidden terms present (a wrong number, a renamed site).
    * ``abstained`` — the answer declined instead of answering.

    ``numbered=True`` reads ``[n]`` as the n-th entry of ``valid_sources``.
    Validity and precision are 0 when nothing is cited: an uncited answer is
    unsupported by construction. Recall is 0 then too, unless nothing was
    relevant to cite.
    """
    valid = {_norm_id(s) for s in valid_sources}
    relevant = {_norm_id(s) for s in (relevant_sources or [])}
    numbered_sources = list(valid_sources) if numbered else None

    def present(term: str) -> bool:
        return term in model_output if case_sensitive_terms else term.lower() in model_output.lower()

    cites = extract_citations(model_output, numbered_sources=numbered_sources)
    n = len(cites)
    fabricated = [c for c in cites if c not in valid]
    required = required_terms or []
    return {
        "n_citations": n,
        "citation_validity": (n - len(fabricated)) / n if n else 0.0,
        "citation_precision": sum(1 for c in cites if c in relevant) / n if n else 0.0,
        "citation_recall": (
            sum(1 for r in relevant if r in cites) / len(relevant) if relevant else (0.0 if cites else 1.0)
        ),
        "fabricated": fabricated,
        "fact_coverage": sum(1 for t in required if present(t)) / len(required) if required else 1.0,
        "n_forbidden": sum(1 for t in (forbidden_terms or []) if present(t)),
        "abstained": is_abstention(model_output, numbered_sources=numbered_sources),
    }


def make_attribution_scorer(
    *,
    valid_sources: list[str],
    relevant_sources: list[str] | None = None,
    required_terms: list[str] | None = None,
    forbidden_terms: list[str] | None = None,
    weights: dict[str, float] | None = None,
    numbered: bool = False,
    case_sensitive_terms: bool = True,
) -> Callable[[str, Any], float]:
    """Scalar attribution score with an auditable ``.breakdown`` attribute.

    ``score = w_validity·validity + w_recall·recall + w_coverage·coverage
    − 0.25·n_forbidden``, clipped to [0, 1]; the weights default to a third
    each. Precision is reported in the breakdown but not blended, so citing an
    extra provided-but-irrelevant source is visible without being punished
    twice.
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
            numbered=numbered,
            case_sensitive_terms=case_sensitive_terms,
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


def make_abstention_scorer(*, answerable: bool) -> Callable[[str, Any], float]:
    """Score a query that may or may not be answerable from the provided sources.

    * ``answerable=False``: 1.0 for a clean abstention (sentinel, no
      citations), 0.0 otherwise; any citation is a confabulated relevance claim.
    * ``answerable=True`` (``gold`` = relevant ids): 0.0 for an abstention,
      otherwise the fraction of gold ids cited or ranked anywhere in the
      response. Declining is never free.

    The rule is proper: a model maximises its expected score only by
    abstaining exactly when it has no relevant evidence.
    """

    def scorer(model_output: str, gold: Any) -> float:
        abstained = is_abstention(model_output)
        if not answerable:
            return 1.0 if abstained else 0.0
        if abstained:
            return 0.0
        relevant = {_norm_id(x) for x in (gold or [])}
        if not relevant:
            return 0.0
        cited = {_norm_id(x) for x in _parse_ranked_list(model_output)}
        cited |= set(extract_citations(model_output))
        return sum(1 for r in relevant if r in cited) / len(relevant)

    return scorer


def make_scorer_from_spec(spec: dict[str, Any]) -> Callable[[str, Any], float]:
    """Reconstruct a Family-1 scorer callable from a JSON-serializable spec.

    Recognised names: ``retrieval_metrics``, ``term_preservation``,
    ``citation_support``, ``attribution``, ``abstention``, ``zero``.
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
    if name == "attribution":
        return make_attribution_scorer(
            valid_sources=config["valid_sources"],
            relevant_sources=config.get("relevant_sources"),
            required_terms=config.get("required_terms"),
            forbidden_terms=config.get("forbidden_terms"),
            weights=config.get("weights"),
            numbered=bool(config.get("numbered", False)),
            case_sensitive_terms=bool(config.get("case_sensitive_terms", True)),
        )
    if name == "abstention":
        return make_abstention_scorer(answerable=bool(config.get("answerable", True)))
    if name == "zero":
        return lambda _out, _gold: 0.0
    raise ValueError(f"unknown scorer name: {name!r}")
