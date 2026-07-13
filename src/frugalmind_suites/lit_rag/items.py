"""Literature / RAG / translation suites (Family 1), verifiable-core.

Three thin suites over one truth set (`tasks.yaml`), one per deterministic
scorer, mirroring the STA/LTA one-suite-per-kind structure. Each task in the
YAML carries its own serialisable ``scorer`` spec, so ``_compose`` is trivial
and ``items()``/``export_rows()`` share a single source of truth.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import yaml

from frugalmind import DenolleGroupSuite, TaskKind
from frugalmind.export import BenchmarkRow

from .scorers import make_scorer_from_spec

_DEFAULT_TASKS = Path(__file__).parent / "tasks.yaml"
TASKS_PATH = Path(os.environ.get("FM_LITRAG_TASKS", _DEFAULT_TASKS))

VALID_SPLITS = ("validation", "test")
VALID_VISIBILITIES = ("public", "private")


def _resolve_split(split: str | None) -> str | None:
    if split is None:
        env = os.environ.get("FM_LITRAG_SPLIT")
        if env in (None, "", "all"):
            return None
        split = env
    if split not in VALID_SPLITS:
        raise ValueError(f"split must be one of {VALID_SPLITS} or None; got {split!r}")
    return split


def _load_tasks(kind: str, split: str | None = None) -> list[dict]:
    if not TASKS_PATH.exists():
        raise FileNotFoundError(f"{TASKS_PATH} not found")
    data = yaml.safe_load(TASKS_PATH.read_text())
    tasks = data["tasks"]
    for t in tasks:
        for required in ("id", "kind", "prompt", "gold", "scorer", "split", "visibility"):
            if required not in t:
                raise ValueError(f"task {t.get('id')!r} missing key {required!r}")
    tasks = [t for t in tasks if t["kind"] == kind]
    split = _resolve_split(split)
    if split is not None:
        tasks = [t for t in tasks if t["split"] == split]
    return tasks


class _LitRagSuite(DenolleGroupSuite):
    """Base: filter one truth set by ``_kind`` and split; scorer from the row."""

    _kind: str
    dataset_id = "lit_rag"

    def __init__(self, *, split: str | None = None) -> None:
        self.split = _resolve_split(split)

    def _tasks(self) -> list[dict]:
        return _load_tasks(self._kind, split=self.split)

    def _compose(self, t: dict) -> tuple[str, Any, dict, dict]:
        prompt = t["prompt"].strip()
        gold = t["gold"]
        scorer_spec = t["scorer"]
        meta = {"task_id": t["id"], "kind": t["kind"]}
        return prompt, gold, scorer_spec, meta

    def items(self) -> Iterable[tuple[str, Any, Callable[[str, Any], float]]]:
        for t in self._tasks():
            prompt, gold, scorer_spec, _ = self._compose(t)
            yield (prompt, gold, make_scorer_from_spec(scorer_spec))

    def export_rows(self) -> Iterable[BenchmarkRow]:
        for t in self._tasks():
            prompt, gold, scorer_spec, meta = self._compose(t)
            yield BenchmarkRow(
                id=f"{self.dataset_id}/{self.suite_id}/{t['id']}",
                dataset_id=self.dataset_id,
                suite_id=self.suite_id,
                version=self.version,
                task_kind=self.task_kind.value,
                split=t["split"],
                visibility=t["visibility"],
                prompt=prompt,
                gold=gold,
                scorer_spec=scorer_spec,
                metadata=meta,
            )


class LitRagRetrievalSuite(_LitRagSuite):
    """RAG retrieval: rank documents against a gold relevant set."""

    _kind = "retrieval"
    task_kind = TaskKind.RETRIEVAL
    suite_id = "retrieval"
    version = "v0.1"


class LitRagTranslationSuite(_LitRagSuite):
    """Translation with domain-term preservation."""

    _kind = "translation"
    task_kind = TaskKind.TRANSLATION
    suite_id = "translation"
    version = "v0.1"


class LitRagGroundedQASuite(_LitRagSuite):
    """Grounded QA: citation-supported answers, no fabricated sources."""

    _kind = "grounded_qa"
    task_kind = TaskKind.GROUNDED_QA
    suite_id = "grounded_qa"
    version = "v0.1"


ALL_SUITES = (
    LitRagRetrievalSuite,
    LitRagTranslationSuite,
    LitRagGroundedQASuite,
)


# --------------------------------------------------------------------------- #
# Known-item retrieval over a corpus of REAL arXiv papers (document family).
#
# The seed tasks above are one-item demonstrations of each scorer. THIS suite is
# the real document-based evaluation: 12 research questions, each answered by
# exactly one paper in a shortlist of 10 same-domain candidates. Relevance is
# objective (the paper the question was written from), so it is scored at T0 by
# `retrieval_metrics` with no judge and no human labels.
# --------------------------------------------------------------------------- #
_CORPUS_PATH = Path(__file__).parent / "data" / "arxiv_geo_corpus.json"
_QUERIES_PATH = Path(__file__).parent / "queries.yaml"


def _load_known_item() -> tuple[dict, list[dict], list[dict]]:
    import json

    corpus_doc = json.loads(_CORPUS_PATH.read_text())
    docs = corpus_doc["docs"]
    qdoc = yaml.safe_load(_QUERIES_PATH.read_text())
    return qdoc.get("meta", {}), qdoc["queries"], docs


_STOP = frozenset(
    "a an the of for and or to in on with we our this that is are be by from as at "
    "using use used propose proposed present presents new novel method methods "
    "results show shows can it its their they which than then also more most such "
    "these those has have been was were will would".split()
)


def _terms(doc: dict) -> set[str]:
    text = f"{doc['title']} {doc['abstract']}".lower()
    return {
        w
        for w in "".join(c if c.isalnum() else " " for c in text).split()
        if len(w) > 3 and w not in _STOP
    }


def _shortlist(target_id: str, docs: list[dict], k: int) -> list[dict]:
    """Target + (k-1) HARD distractors: the most confusable papers in the corpus.

    Sampling distractors at random makes this eval trivial and, worse, actively
    misleading. The queries name distinctive entities (Santorini, the Moon,
    Fourier neural operators); if no distractor shares them, the task is solvable
    by keyword matching alone. Measured: both claude-haiku AND qwen2.5:7b scored a
    perfect 1.000 unskilled — no discrimination — and the skill, which teaches
    "rank by contribution, not shared vocabulary", *lowered* qwen's score by
    talking it out of the winning shortcut.

    So distractors are the nearest neighbours of the target by term overlap
    (Jaccard over content words). They share the target's vocabulary and topic,
    which forces the model to discriminate on the actual contribution — which is
    what the task is supposed to measure.

    Deterministic: the same item always shows the same candidates.
    """
    import hashlib

    target = next(d for d in docs if d["arxiv_id"] == target_id)
    t_terms = _terms(target)

    def similarity(d: dict) -> float:
        o = _terms(d)
        union = t_terms | o
        return len(t_terms & o) / len(union) if union else 0.0

    others = [d for d in docs if d["arxiv_id"] != target_id]
    # Sort by similarity desc; break ties deterministically by id hash.
    others.sort(
        key=lambda d: (
            -similarity(d),
            hashlib.sha256(f"{target_id}|{d['arxiv_id']}".encode()).hexdigest(),
        )
    )
    picked = others[: k - 1]
    shortlist = [target, *picked]
    # Deterministic display order, so the gold is not always first.
    shortlist.sort(key=lambda d: hashlib.sha256((target_id + d["arxiv_id"]).encode()).hexdigest())
    return shortlist


class LitRagKnownItemSuite(DenolleGroupSuite):
    """Research question -> rank candidate papers; gold is the paper it came from."""

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
        shortlist = _shortlist(q["gold"], docs, k)

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
