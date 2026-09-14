"""Non-agentic baselines for the RCA suite (ABC R.13, AAM trivial baselines).

``do_nothing`` lives in ``solvers.py``. This module adds the lexical control:

``bm25_only``  Okapi BM25 over a JSON corpus (the aRCADA catalog or paper
               index converted by ``scripts/rca_build_corpus.py``), returning
               the top-k document ids as a JSON array. aRCADA's deployed
               retriever is MiniSearch (BM25-based); this is the same
               retrieval class with no model behind it, so it is the natural
               non-agentic control for T3 and the *leakage detector* for
               catalog-derived items: any item this baseline answers at
               chance-or-better on the test split has leaked (DESIGN.md §3.4).

Pure Python, no dependencies beyond the standard library and ``inspect_ai``
for the solver wrapper. The retriever class is importable without Inspect.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-_:][a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


class BM25:
    """Okapi BM25 (k1=1.5, b=0.75) over ``{id: text}``."""

    def __init__(self, docs: dict[str, str], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.ids = list(docs)
        self.tf: list[Counter[str]] = []
        self.dl: list[int] = []
        df: Counter[str] = Counter()
        for i in self.ids:
            toks = tokenize(docs[i])
            c = Counter(toks)
            self.tf.append(c)
            self.dl.append(len(toks))
            df.update(c.keys())
        n = max(1, len(self.ids))
        self.avgdl = (sum(self.dl) / n) if n else 0.0
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def score(self, query: str) -> list[tuple[str, float]]:
        q = tokenize(query)
        out = []
        for idx, doc_id in enumerate(self.ids):
            tf, dl = self.tf[idx], self.dl[idx]
            s = 0.0
            for t in q:
                if t not in tf:
                    continue
                f = tf[t]
                denom = f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1.0))
                s += self.idf.get(t, 0.0) * f * (self.k1 + 1) / denom
            out.append((doc_id, s))
        out.sort(key=lambda x: (-x[1], x[0]))
        return out

    def top_k(self, query: str, k: int = 10) -> list[str]:
        return [d for d, s in self.score(query)[:k] if s > 0]


def load_corpus(path: str | Path) -> dict[str, str]:
    """Accept the frugalmind lit_rag corpus shape (``{"documents": [{id,title,abstract,...}]}``)
    or a plain ``{id: text}`` mapping."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "documents" in data:
        return {
            str(d["id"]): " ".join(
                str(d.get(k, "")) for k in ("title", "abstract", "keywords", "text")
            )
            for d in data["documents"]
        }
    if isinstance(data, dict):
        return {str(k): str(v) for k, v in data.items()}
    raise ValueError(f"unrecognised corpus shape in {path}")


def bm25_only(corpus_path: str, k: int = 10):
    """Inspect solver: answer every prompt with the BM25 top-k ids as JSON."""
    from inspect_ai.model import ModelOutput
    from inspect_ai.solver import Generate, Solver, TaskState, solver

    index = BM25(load_corpus(corpus_path))

    @solver
    def _bm25() -> Solver:
        async def solve(state: TaskState, generate: Generate) -> TaskState:
            ids = index.top_k(state.input_text, k=k)
            state.output = ModelOutput.from_content(model="bm25_only", content=json.dumps(ids))
            return state

        return solve

    return _bm25()


__all__ = ["BM25", "bm25_only", "load_corpus", "tokenize"]
