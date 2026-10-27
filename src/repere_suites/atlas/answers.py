"""Score answers to RCA Atlas questions with Repère's attribution scorer.

The gold lives in RCA Atlas (``rca_eval_gold``, pulled by ``fetch_atlas``);
this module only turns one gold record, plus the numbered list of sources the
model was shown, into a ``scorer_spec`` for
``repere_suites.lit_rag.scorers.make_scorer_from_spec``. No Atlas row is
stored here.

Matching follows Atlas's own answer checks (``atlas_eval/suites/live.py``
at the pinned commit), so the two harnesses agree on what counts:

* citations are numbered, ``[n]`` pointing at the n-th listed source;
* a required citation is met when a listed source has its ``source_id`` or
  its URL (trailing slash and case ignored);
* one deliberate difference: a required citation with neither a
  ``source_id`` nor a URL is matched on its exact title (case ignored). At
  the pinned commit 2 of the 25 required citations are title-only, which
  Atlas's own check can never count as cited; that is a gold defect to fix
  upstream, and until then matching the title is the fair reading;
* required entities are matched case-insensitively.

What Repère adds is the breakdown Atlas does not report: citation precision,
the list of fabricated references, and a scalar that puts validity, recall
and entity coverage on one scale with the auditable parts kept separate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

RANKED_REVIEW_STATUS = "corpus_verified"


def _url(value: Any) -> str:
    return str(value or "").rstrip("/").lower()


def _cites(source: Mapping[str, Any], sid: str, url: str, title: str) -> bool:
    """Does a listed source satisfy a required citation (id, else URL, else title)?"""
    return bool(
        (sid and str(source.get("id", "")).lower() == sid.lower())
        or (url and _url(source.get("url")) == url)
        or (title and str(source.get("title", "")).strip().lower() == title)
    )


def is_ranked(gold: Mapping[str, Any]) -> bool:
    """Only corpus-verified gold may feed a ranked number.

    Atlas marks unchecked gold ``requires_human_review``; those rows are
    drafts until a second person verifies them (the RCA lifecycle in
    ``docs/rca/AUTHORING.md``).
    """
    return gold.get("review_status") == RANKED_REVIEW_STATUS


def relevant_source_ids(gold: Mapping[str, Any], sources: Sequence[Mapping[str, Any]]) -> list[str]:
    """The listed source each required citation resolves to.

    A required citation that matches no listed source keeps its own
    ``source_id``: it stays in the relevant set, so recall cannot reach 1.0
    when retrieval never surfaced it. That is a retrieval miss, and the
    score should show it.
    """
    out: list[str] = []
    for need in gold.get("required_citations") or []:
        sid, url = str(need.get("source_id") or ""), _url(need.get("url"))
        title = "" if (sid or url) else str(need.get("title") or "").strip().lower()
        fallback = sid or url or (f"title:{title}" if title else "")
        match = next((str(s.get("id")) for s in sources if _cites(s, sid, url, title)), fallback)
        if match and match not in out:
            out.append(match)
    return out


def answer_attribution_spec(
    gold: Mapping[str, Any],
    sources: Sequence[Mapping[str, Any]],
    *,
    weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """``scorer_spec`` for one Atlas answer.

    ``sources`` is the numbered evidence list exactly as the model saw it,
    each with an ``id`` and optionally a ``url``.
    """
    if not sources:
        raise ValueError("an attribution score needs the numbered source list the model was shown")
    config: dict[str, Any] = {
        "valid_sources": [str(s["id"]) for s in sources],
        "relevant_sources": relevant_source_ids(gold, sources),
        "required_terms": list(gold.get("required_entity_ids") or []),
        "numbered": True,
        "case_sensitive_terms": False,
    }
    if weights:
        config["weights"] = dict(weights)
    return {"name": "attribution", "config": config}


__all__ = ["RANKED_REVIEW_STATUS", "answer_attribution_spec", "is_ranked", "relevant_source_ids"]
