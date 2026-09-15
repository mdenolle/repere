#!/usr/bin/env python3
"""Build the OOI-RCA literature corpus for the lit_rag suite from aRCADA.

aRCADA (https://github.com/mhemmett/arcada) maintains the group's Zotero
"OOI RCA" collection as ``catalog/papers.json``: real papers, real DOIs. This
script freezes that file into the corpus schema read by
``frugalmind.agents.literature.load_corpus`` and stamps provenance (source
commit + sha256) so a leaderboard row can be pinned to the exact corpus
version it was scored against.

Usage::

    python scripts/build_ooi_rca_corpus.py /path/to/arcada
    python scripts/build_ooi_rca_corpus.py /path/to/arcada --out custom.json

The document ``id`` is the DOI, which is also the id aRCADA's own index uses
(``paper::<doi>``), so an eval item's gold refers to the same key the deployed
system cites. ``pdf_path`` (a local filesystem path) is dropped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "frugalmind_suites"
    / "lit_rag"
    / "data"
    / "ooi_rca_corpus.json"
)


def _slug(paper: dict) -> str:
    words = re.findall(r"[a-z0-9]+", paper["title"].lower())[:6]
    author = re.sub(r"[^a-z0-9]", "", (paper.get("first_author") or "anon").lower())
    return f"nodoi:{author}-{paper.get('year') or 'nd'}-{'-'.join(words)}"


def _git_commit(repo: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def build(arcada_root: Path) -> dict:
    src = arcada_root / "catalog" / "papers.json"
    raw = src.read_bytes()
    papers = json.loads(raw)["papers"]

    documents: list[dict] = []
    seen: set[str] = set()
    for p in papers:
        if not p.get("title") or p.get("year") is None:
            continue
        doi = (p.get("doi") or "").strip() or None
        doc_id = doi or _slug(p)
        if doc_id in seen:
            raise ValueError(f"duplicate document id: {doc_id!r}")
        seen.add(doc_id)
        documents.append(
            {
                "id": doc_id,
                "doi": doi,
                "title": p["title"].strip(),
                "abstract": (p.get("abstract") or "").strip(),
                "year": int(p["year"]),
                "journal": p.get("journal"),
                "first_author": p.get("first_author"),
                "keywords": list(p.get("tags") or []),
                "linked_instruments": list(p.get("linked_instruments") or []),
            }
        )
    documents.sort(key=lambda d: (-d["year"], d["id"]))

    return {
        "corpus_id": "ooi_rca_zotero",
        "schema": "frugalmind.lit_rag.corpus.v1",
        "note": (
            "Real OOI Regional Cabled Array literature: titles, abstracts and "
            "DOIs from the aRCADA project's Zotero 'OOI RCA' collection. "
            "Nothing here is synthetic. Publication dates are year-only, so "
            "cutoff_date filtering compares by year unless `published` is set."
        ),
        "source": {
            "repo": "https://github.com/mhemmett/arcada",
            "file": "catalog/papers.json",
            "commit": _git_commit(arcada_root),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "n_documents": len(documents),
        "n_without_abstract": sum(1 for d in documents if len(d["abstract"]) < 80),
        "documents": documents,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("arcada_root", type=Path, help="local checkout of mhemmett/arcada")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    corpus = build(args.arcada_root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(corpus, indent=2, ensure_ascii=False) + "\n")
    print(
        f"wrote {corpus['n_documents']} documents "
        f"({corpus['n_without_abstract']} without a usable abstract) -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
