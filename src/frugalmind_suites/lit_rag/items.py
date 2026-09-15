"""Literature / RAG / translation suites (Family 1), verifiable-core.

Two real corpora, one suite family:

* **OOI-RCA** (``ooi_rca.yaml`` over ``data/ooi_rca_corpus.json``) — the
  literature the deployed aRCADA assistant retrieves over. Four kinds share
  one truth set: ``known_item`` retrieval, ``abstention`` (unanswerable
  queries plus matched answerable controls), ``grounded_qa`` (facts verbatim
  in one abstract, cited by DOI) and ``translation`` (identifiers survive).
* **arXiv physics.geo-ph** (``queries.yaml`` over ``data/arxiv_geo_corpus.json``)
  — known-item retrieval over a broader seismology corpus.

Every item's gold is objective (the paper a question was written from, a
number that appears in an abstract, the absence of any paper on a topic), so
all scoring is tier T0 with no judge. Candidates shown to the model are
**hard distractors** — the corpus documents most confusable with the target —
because random distractors make the task solvable by keyword matching alone
(measured: two models scored a perfect 1.0 unskilled; see ``_hard_shortlist``).

The committed truth set is the public validation split. A hidden test split
in the same schema is merged from ``FM_EVAL_DATA_DIR`` when present, mirroring
``synthetic_stalta``.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from frugalmind import DenolleGroupSuite, TaskKind
from frugalmind.agents.literature import Document, load_corpus
from frugalmind.export import BenchmarkRow

from .scorers import ABSTAIN_SENTINEL, make_scorer_from_spec

_HERE = Path(__file__).parent
_DEFAULT_TRUTH = _HERE / "ooi_rca.yaml"
TRUTH_PATH = Path(os.environ.get("FM_LITRAG_TASKS", _DEFAULT_TRUTH))

# Hidden test split: same schema, never committed. See
# docs/golden_data_provisioning.md for how to hold and pull it.
_REPO = Path(__file__).resolve().parents[3]
PRIVATE_DIR = Path(os.environ.get("FM_EVAL_DATA_DIR", _REPO / "data" / "private"))
HIDDEN_TRUTH_PATH = PRIVATE_DIR / "lit_rag_ooi_rca_test.yaml"

VALID_SPLITS = ("validation", "test")
VALID_VISIBILITIES = ("public", "private")
VALID_KINDS = ("known_item", "abstention", "grounded_qa", "translation")

_REQUIRED_KEYS = ("id", "kind", "split", "visibility")


def _resolve_split(split: str | None) -> str | None:
    if split is None:
        env = os.environ.get("FM_LITRAG_SPLIT")
        if env in (None, "", "all"):
            return None
        split = env
    if split not in VALID_SPLITS:
        raise ValueError(f"split must be one of {VALID_SPLITS} or None; got {split!r}")
    return split


def _validate_item(item: dict) -> None:
    for k in _REQUIRED_KEYS:
        if k not in item:
            raise ValueError(f"lit_rag item {item.get('id')!r} missing key {k!r}")
    if item["kind"] not in VALID_KINDS:
        raise ValueError(f"lit_rag item {item['id']!r}: unknown kind {item['kind']!r}")
    if item["split"] not in VALID_SPLITS or item["visibility"] not in VALID_VISIBILITIES:
        raise ValueError(f"lit_rag item {item['id']!r}: bad split/visibility")
    if item["kind"] == "translation":
        for k in ("text", "target_language", "required_terms"):
            if k not in item:
                raise ValueError(f"translation item {item['id']!r} missing key {k!r}")
    else:
        if "query" not in item or "gold" not in item:
            raise ValueError(f"item {item['id']!r} needs `query` and `gold`")
        if item.get("answerable", True) and not item["gold"]:
            raise ValueError(f"item {item['id']!r} is answerable but has empty gold")
        if not item.get("answerable", True) and item["gold"]:
            raise ValueError(f"item {item['id']!r} is unanswerable but has gold")


def _load_truth(split: str | None = None) -> tuple[dict, list[dict]]:
    if not TRUTH_PATH.exists():
        raise FileNotFoundError(f"{TRUTH_PATH} not found")
    doc = yaml.safe_load(TRUTH_PATH.read_text())
    meta, items = dict(doc.get("meta", {})), list(doc["items"])

    if HIDDEN_TRUTH_PATH.exists():
        hidden = yaml.safe_load(HIDDEN_TRUTH_PATH.read_text()) or {}
        items.extend(hidden.get("items", []))

    for it in items:
        _validate_item(it)

    split = _resolve_split(split)
    if split == "test" and not any(it["split"] == "test" for it in items):
        raise FileNotFoundError(
            "the hidden lit_rag test split is not available locally.\n"
            f"  expected: {HIDDEN_TRUTH_PATH}\n"
            "  pull it (requires access to the gated dataset):\n"
            "      pixi run -e full python scripts/pull_eval_data.py\n"
            "  Ranked scores are computed on the hidden split only; the public "
            "`validation` split is for development."
        )
    if split is not None:
        items = [it for it in items if it["split"] == split]
    return meta, items


@lru_cache(maxsize=4)
def _corpus_docs(path: str) -> tuple[Document, ...]:
    return tuple(load_corpus(path))


def _corpus_for(meta: dict) -> tuple[Document, ...]:
    rel = meta.get("corpus", "data/ooi_rca_corpus.json")
    return _corpus_docs(str((TRUTH_PATH.parent / rel).resolve()))


# --------------------------------------------------------------------------- #
# Hard-distractor shortlists
# --------------------------------------------------------------------------- #
_STOP = frozenset(
    "a an the of for and or to in on with we our this that is are be by from as at "
    "using use used propose proposed present presents new novel method methods "
    "results show shows can it its their they which than then also more most such "
    "these those has have been was were will would".split()
)


def _content_terms(text: str) -> set[str]:
    return {
        w
        for w in "".join(c if c.isalnum() else " " for c in text.lower()).split()
        if len(w) > 3 and w not in _STOP
    }


def _hard_shortlist(
    reference_terms: set[str],
    pool: dict[str, set[str]],
    *,
    include: list[str],
    k: int,
    seed: str,
) -> list[str]:
    """``include`` + the (k − len(include)) pool ids most confusable with the reference.

    Confusability is Jaccard overlap of content words. Sampling distractors at
    random makes the eval trivial and actively misleading: queries name
    distinctive entities and, if no distractor shares them, keyword matching
    alone solves the task. Nearest neighbours force the model to discriminate
    on the actual contribution. Deterministic: ties break on a hash of
    ``seed`` + id, and the display order is a hash too so the gold does not
    always sit in the same slot.
    """

    def similarity(terms: set[str]) -> float:
        union = reference_terms | terms
        return len(reference_terms & terms) / len(union) if union else 0.0

    others = [i for i in pool if i not in include]
    others.sort(
        key=lambda i: (
            -similarity(pool[i]),
            hashlib.sha256(f"{seed}|{i}".encode()).hexdigest(),
        )
    )
    picked = [*include, *others[: max(0, k - len(include))]]
    picked.sort(key=lambda i: hashlib.sha256(f"{seed}{i}".encode()).hexdigest())
    return picked


def _doc_terms(docs: Iterable[Document]) -> dict[str, set[str]]:
    return {d.id: _content_terms(f"{d.title} {d.abstract}") for d in docs}


def _render_sources(docs: list[Document]) -> str:
    lines = []
    for d in docs:
        lines.append(
            f'  ["{d.id}"] {d.title} — {d.citation}\n      {d.abstract or "(no abstract available)"}'
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# OOI-RCA suites
# --------------------------------------------------------------------------- #
class _OOIRCASuite(DenolleGroupSuite):
    """Base: one ``kind`` filtered from ``ooi_rca.yaml``; scorer from the row."""

    _kind: str
    dataset_id = "lit_rag"
    version = "v0.1"

    def __init__(self, *, split: str | None = None) -> None:
        self.split = _resolve_split(split)

    # -- data access -------------------------------------------------------
    def _load(self) -> tuple[dict, list[dict]]:
        return _load_truth(split=self.split)

    def _select(self, items: list[dict]) -> list[dict]:
        return [it for it in items if it["kind"] == self._kind]

    def _items(self) -> list[dict]:
        meta, items = self._load()
        return self._select(items)

    def _docs_by_id(self, meta: dict) -> dict[str, Document]:
        return {d.id: d for d in _corpus_for(meta)}

    # -- prompt assembly ---------------------------------------------------
    def _candidates(self, item: dict, meta: dict, k: int) -> list[Document]:
        """Gold + hard distractors (or, unanswerable, the nearest neighbours of the query)."""
        by_id = self._docs_by_id(meta)
        pool = _doc_terms(by_id.values())
        gold = [str(g) for g in item.get("gold") or []]
        for g in gold:
            if g not in by_id:
                raise ValueError(f"item {item['id']!r}: gold id {g!r} not in corpus")
        if gold:
            ref: set[str] = set()
            for g in gold:
                ref |= pool[g]
        else:
            ref = _content_terms(item["query"])
        ids = _hard_shortlist(ref, pool, include=gold, k=k, seed=item["id"])
        return [by_id[i] for i in ids]

    def _base_meta(self, item: dict, meta: dict) -> dict:
        m = {
            "task_id": item["id"],
            "kind": item["kind"],
            "corpus_id": meta.get("corpus_id"),
            "answerable": bool(item.get("answerable", True)),
            "cutoff_date": item.get("cutoff_date"),
        }
        m.update(item.get("metadata") or {})
        return m

    def _compose(self, item: dict, meta: dict) -> tuple[str, Any, dict, dict]:
        raise NotImplementedError

    # -- public surface ----------------------------------------------------
    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        meta, items = self._load()
        for it in self._select(items):
            prompt, gold, spec, _ = self._compose(it, meta)
            yield (prompt, gold, make_scorer_from_spec(spec))

    def export_rows(self) -> Iterable[BenchmarkRow]:
        meta, items = self._load()
        for it in self._select(items):
            prompt, gold, spec, m = self._compose(it, meta)
            yield BenchmarkRow(
                id=f"{self.dataset_id}/{self.suite_id}/{it['id']}",
                dataset_id=self.dataset_id,
                suite_id=self.suite_id,
                version=self.version,
                task_kind=self.task_kind.value,
                split=it["split"],
                visibility=it["visibility"],
                prompt=prompt,
                gold=gold,
                scorer_spec=spec,
                metadata=m,
            )


class LitRagRetrievalSuite(_OOIRCASuite):
    """Known-item retrieval over the OOI-RCA corpus: rank a hard shortlist."""

    _kind = "known_item"
    task_kind = TaskKind.RETRIEVAL
    suite_id = "ooi_rca_retrieval"

    def _compose(self, item: dict, meta: dict) -> tuple[str, Any, dict, dict]:
        k = int(meta.get("candidates_per_item", 10))
        cands = self._candidates(item, meta, k)
        prompt = (
            "You are given a research question and a shortlist of candidate "
            "papers from the OOI Regional Cabled Array literature. Rank ALL of "
            "the candidates from most to least relevant to the question.\n\n"
            f"Question:\n  {' '.join(item['query'].split())}\n\n"
            f"Candidate papers:\n{_render_sources(cands)}\n\n"
            "Return ONLY a JSON array of the candidate ids (the DOIs), best "
            'first, e.g.\n  ["10.1126/science.aah5563", "10.1130/G39978.1", ...]\n'
            "Include every candidate exactly once. Return nothing but the array."
        )
        gold = [str(g) for g in item["gold"]]
        spec = {"name": "retrieval_metrics", "config": {"metric": "mrr", "k": k}}
        m = self._base_meta(item, meta)
        m["n_candidates"] = len(cands)
        return prompt, gold, spec, m


class LitRagAbstentionSuite(_OOIRCASuite):
    """Decline when nothing is relevant; answer when something is.

    Items: every ``abstention`` row (unanswerable by construction) plus the
    ``known_item`` rows flagged ``abstention_control: true`` (answerable
    matches). Both go through the same prompt and the same proper scoring
    rule, so the suite measures the *decision*, not just recall.
    """

    _kind = "abstention"
    task_kind = TaskKind.RETRIEVAL
    suite_id = "ooi_rca_abstention"

    def _select(self, items: list[dict]) -> list[dict]:
        return [
            it
            for it in items
            if it["kind"] == "abstention"
            or (it["kind"] == "known_item" and it.get("abstention_control"))
        ]

    def _compose(self, item: dict, meta: dict) -> tuple[str, Any, dict, dict]:
        k = int(meta.get("candidates_per_item", 10))
        sentinel = meta.get("sentinel", ABSTAIN_SENTINEL)
        cands = self._candidates(item, meta, k)
        prompt = (
            "You are given a research question and a shortlist of candidate "
            "papers retrieved from the OOI Regional Cabled Array literature. "
            "Some shortlists contain no paper that addresses the question.\n\n"
            f"Question:\n  {' '.join(item['query'].split())}\n\n"
            f"Candidate papers:\n{_render_sources(cands)}\n\n"
            "If one or more candidates address the question, return ONLY a "
            "JSON array of their ids (the DOIs), most relevant first. If NONE "
            f"of the candidates addresses the question, reply with exactly\n  {sentinel}\n"
            "and nothing else. Do not list a paper merely because it shares "
            "vocabulary with the question."
        )
        answerable = bool(item.get("answerable", True))
        gold = [str(g) for g in item.get("gold") or []]
        spec = {"name": "abstention", "config": {"answerable": answerable}}
        m = self._base_meta(item, meta)
        m["n_candidates"] = len(cands)
        m["sentinel"] = sentinel
        return prompt, gold, spec, m


class LitRagGroundedQASuite(_OOIRCASuite):
    """Grounded QA over real abstracts: cite by DOI, facts verbatim, or decline."""

    _kind = "grounded_qa"
    task_kind = TaskKind.GROUNDED_QA
    suite_id = "ooi_rca_grounded_qa"

    def _compose(self, item: dict, meta: dict) -> tuple[str, Any, dict, dict]:
        k = int(meta.get("sources_per_item", 6))
        sentinel = meta.get("sentinel", ABSTAIN_SENTINEL)
        by_id = self._docs_by_id(meta)
        gold = [str(g) for g in item.get("gold") or []]
        if item.get("sources"):
            ids = [str(s) for s in item["sources"]]
            missing = [i for i in ids if i not in by_id]
            if missing:
                raise ValueError(f"item {item['id']!r}: sources not in corpus: {missing}")
            if any(g not in ids for g in gold):
                raise ValueError(f"item {item['id']!r}: gold must be among `sources`")
            # Authoring order lists the gold first; display order must not.
            ids.sort(key=lambda i: hashlib.sha256(f"{item['id']}{i}".encode()).hexdigest())
            sources = [by_id[i] for i in ids]
        else:
            sources = self._candidates(item, meta, k)
        source_ids = [d.id for d in sources]

        prompt = (
            "Answer the question using ONLY the sources below. Write 2-4 "
            "sentences. Cite the source for every claim inline by putting its "
            "id in square brackets, e.g. [10.1126/science.aah5563]. Do not cite "
            "any id that is not listed. Quote numbers and dates exactly as the "
            "source gives them.\n"
            f"If the sources do not contain the answer, reply with exactly\n  {sentinel}\n"
            "and nothing else.\n\n"
            f"Question:\n  {' '.join(item['query'].split())}\n\n"
            f"Sources:\n{_render_sources(sources)}"
        )
        answerable = bool(item.get("answerable", True))
        if answerable:
            spec = {
                "name": "attribution",
                "config": {
                    "valid_sources": source_ids,
                    "relevant_sources": gold,
                    "required_terms": list(item.get("required_terms") or []),
                    "forbidden_terms": list(item.get("forbidden_terms") or []),
                },
            }
        else:
            spec = {"name": "abstention", "config": {"answerable": False}}
        m = self._base_meta(item, meta)
        m["sources"] = source_ids
        m["sentinel"] = sentinel
        return prompt, gold, spec, m


class LitRagTranslationSuite(_OOIRCASuite):
    """Translate a real abstract sentence; identifiers must survive verbatim."""

    _kind = "translation"
    task_kind = TaskKind.TRANSLATION
    suite_id = "ooi_rca_translation"

    def _compose(self, item: dict, meta: dict) -> tuple[str, Any, dict, dict]:
        text = " ".join(item["text"].split())
        prompt = (
            f"Translate the following sentence(s) from a scientific abstract into "
            f"{item['target_language']}. Preserve every identifier exactly as "
            "written: station codes, coordinates, dates, numbers with their "
            "units and punctuation, and place names.\n\n"
            f'"{text}"\n\n'
            "Return only the translation."
        )
        spec = {
            "name": "term_preservation",
            "config": {
                "required_terms": list(item["required_terms"]),
                "forbidden_terms": list(item.get("forbidden_terms") or []),
                "case_sensitive": bool(item.get("case_sensitive", True)),
            },
        }
        m = self._base_meta(item, meta)
        m["source"] = item.get("source")
        m["target_language"] = item["target_language"]
        return prompt, text, spec, m


# --------------------------------------------------------------------------- #
# Known-item retrieval over a corpus of REAL arXiv papers (document family).
# 12 research questions, each answered by exactly one paper in a shortlist of
# 10 same-domain candidates; scored at T0 by `retrieval_metrics` (MRR).
# --------------------------------------------------------------------------- #
_ARXIV_CORPUS_PATH = _HERE / "data" / "arxiv_geo_corpus.json"
_ARXIV_QUERIES_PATH = _HERE / "queries.yaml"


def _load_known_item() -> tuple[dict, list[dict], list[dict]]:
    corpus_doc = json.loads(_ARXIV_CORPUS_PATH.read_text())
    docs = corpus_doc["docs"]
    qdoc = yaml.safe_load(_ARXIV_QUERIES_PATH.read_text())
    return qdoc.get("meta", {}), qdoc["queries"], docs


class LitRagKnownItemSuite(DenolleGroupSuite):
    """Research question -> rank candidate arXiv papers; gold is the paper it came from."""

    task_kind = TaskKind.RETRIEVAL
    dataset_id = "lit_rag"
    suite_id = "known_item_retrieval"
    version = "v0.1"

    def __init__(self, *, split: str | None = None) -> None:
        self.split = _resolve_split(split)

    def _queries(self) -> list[dict]:
        return _load_known_item()[1]

    def _compose(self, q: dict) -> tuple[str, Any, dict, dict]:
        meta, _, docs = _load_known_item()
        k = int(meta.get("candidates_per_item", 10))
        by_id = {d["arxiv_id"]: d for d in docs}
        pool = {d["arxiv_id"]: _content_terms(f"{d['title']} {d['abstract']}") for d in docs}
        ids = _hard_shortlist(pool[q["gold"]], pool, include=[q["gold"]], k=k, seed=q["gold"])
        shortlist = [by_id[i] for i in ids]

        lines = []
        for d in shortlist:
            lines.append(f'  ["{d["arxiv_id"]}"] {d["title"]}\n      {d["abstract"]}')
        candidates = "\n".join(lines)

        prompt = (
            "You are given a research question and a shortlist of candidate "
            "papers. Rank ALL of the candidates from most to least relevant to "
            "the question.\n\n"
            f"Question:\n  {' '.join(q['query'].split())}\n\n"
            f"Candidate papers:\n{candidates}\n\n"
            "Return ONLY a JSON array of the candidate ids, best first, e.g.\n"
            '  ["2203.14386v1", "1810.08517v1", ...]\n'
            "Include every candidate exactly once. Return nothing but the array."
        )
        gold = [q["gold"]]  # exactly one paper answers the question
        scorer_spec = {
            "name": "retrieval_metrics",
            "config": {"metric": meta.get("metric", "mrr"), "k": k},
        }
        item_meta = {"query_id": q["id"], "kind": "retrieval", "n_candidates": k}
        return prompt, gold, scorer_spec, item_meta

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for q in self._queries():
            prompt, gold, spec, _ = self._compose(q)
            yield (prompt, gold, make_scorer_from_spec(spec))

    def export_rows(self) -> Iterable[BenchmarkRow]:
        for q in self._queries():
            prompt, gold, spec, meta = self._compose(q)
            yield BenchmarkRow(
                id=f"{self.dataset_id}/{self.suite_id}/{q['id']}",
                dataset_id=self.dataset_id,
                suite_id=self.suite_id,
                version=self.version,
                task_kind=self.task_kind.value,
                split="validation",
                visibility="public",
                prompt=prompt,
                gold=gold,
                scorer_spec=spec,
                metadata=meta,
            )


ALL_SUITES = (
    LitRagRetrievalSuite,
    LitRagAbstentionSuite,
    LitRagGroundedQASuite,
    LitRagTranslationSuite,
    LitRagKnownItemSuite,
)

__all__ = [
    "ALL_SUITES",
    "HIDDEN_TRUTH_PATH",
    "LitRagAbstentionSuite",
    "LitRagGroundedQASuite",
    "LitRagKnownItemSuite",
    "LitRagRetrievalSuite",
    "LitRagTranslationSuite",
    "TRUTH_PATH",
]
