"""Build the Nature Machine Intelligence manuscript from Markdown.

Single source of truth:
    metadata.yaml   author list, affiliations, required Nature statements
    manuscript.md   the prose
    refs.bib        bibliography (Nature superscript style via csl/nature.csl)

Produces:
    build/frugalmind_nmi.pdf    double-spaced, line-numbered  (submission PDF)
    build/frugalmind_nmi.docx   for co-author review / Word-based submission
    build/frugalmind_nmi.tex    if you ever need to hand it to a LaTeX template

Nature Portfolio does NOT require its own template at initial submission — it
asks for a readable, double-spaced, line-numbered manuscript. That is exactly
what this produces. Strict styling only matters at acceptance.

    python paper/build.py            # both
    python paper/build.py --pdf      # just the PDF
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"

# Double-spaced + line-numbered, per Nature's initial-submission guidance.
PREAMBLE = r"""
\usepackage{setspace}
\doublespacing
\usepackage[left]{lineno}
\linenumbers
\usepackage{microtype}
\renewcommand{\familydefault}{\sfdefault}
\usepackage[margin=1in]{geometry}
"""


def _superscripts(nums: list[int]) -> str:
    return ",".join(str(n) for n in nums)


def build_titleblock(meta: dict) -> dict:
    """Turn the structured author list into what pandoc's template wants."""
    authors, corr = [], []
    for a in meta.get("author", []):
        marks = _superscripts(a.get("affiliation", []))
        star = r"\textsuperscript{*}" if a.get("corresponding") else ""
        authors.append(f"{a['name']}\\textsuperscript{{{marks}}}{star}")
        if a.get("corresponding"):
            corr.append(f"{a['name']} ({a.get('email', 'TODO@email')})")

    # Join affiliations with \\ BETWEEN lines only — a trailing \\ inside
    # flushleft raises "There's no line here to end".
    aff_lines = [
        f"\\textsuperscript{{{a['id']}}}{' '.join(a['name'].split())}"
        for a in meta.get("affiliations", [])
    ]
    before = "\\begin{flushleft}\\small\n" + " \\\\\n".join(aff_lines) + "\n\\end{flushleft}\n"
    if corr:
        before += (
            "\\begin{flushleft}\\small\n"
            "\\textsuperscript{*}Corresponding author: " + "; ".join(corr) + "\n"
            "\\end{flushleft}\n"
        )

    return {
        "title": meta["title"],
        "author": authors,
        "date": "",
        "include-before": [before],
        "header-includes": [PREAMBLE],
        "link-citations": True,
    }


BACKMATTER_ORDER = [
    ("acknowledgements", "Acknowledgements"),
    ("author-contributions", "Author contributions"),
    ("competing-interests", "Competing interests"),
    ("data-availability", "Data availability"),
    ("code-availability", "Code availability"),
]


def build_backmatter(meta: dict) -> str:
    out = []
    for key, heading in BACKMATTER_ORDER:
        if meta.get(key):
            out.append(f"## {heading}\n\n{meta[key].strip()}\n")
    return "\n".join(out)


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(" ".join(cmd), file=sys.stderr)
        print(proc.stdout[-3000:], file=sys.stderr)
        print(proc.stderr[-3000:], file=sys.stderr)
        raise SystemExit(f"build failed: {cmd[0]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--docx", action="store_true")
    args = ap.parse_args()
    do_pdf = args.pdf or not args.docx
    do_docx = args.docx or not args.pdf

    if not shutil.which("pandoc"):
        raise SystemExit("pandoc not found — install it (brew install pandoc)")

    BUILD.mkdir(exist_ok=True)
    meta = yaml.safe_load((HERE / "metadata.yaml").read_text())

    # Generated inputs: a pandoc-shaped title block, and the Nature back matter.
    gen_meta = BUILD / "_titleblock.yaml"
    gen_meta.write_text(
        "---\n" + yaml.safe_dump(build_titleblock(meta), sort_keys=False,
                                 default_flow_style=False, allow_unicode=True) + "---\n"
    )
    gen_back = BUILD / "_backmatter.md"
    gen_back.write_text(build_backmatter(meta))

    common = [
        "pandoc",
        str(gen_meta),
        str(HERE / "manuscript.md"),
        str(gen_back),
        "--citeproc",
        f"--csl={HERE / 'csl' / 'nature.csl'}",
        f"--bibliography={HERE / 'refs.bib'}",
        f"--resource-path={HERE}",
        "--number-sections=false",
    ]

    n_words = len((HERE / "manuscript.md").read_text().split())

    if do_pdf:
        out = BUILD / "frugalmind_nmi.pdf"
        run([*common, "--pdf-engine=xelatex", "-o", str(out)])
        print(f"wrote {out}")
        run([*common, "-s", "-o", str(BUILD / "frugalmind_nmi.tex")])

    if do_docx:
        out = BUILD / "frugalmind_nmi.docx"
        run([*common, "-o", str(out)])
        print(f"wrote {out}")

    # A word count that excludes the back matter and figure/table legends is what
    # Nature actually limits (~5,000 for an Article). This is a rough upper bound.
    print(f"\nmanuscript.md ~{n_words} words (incl. Methods, legends, tables)")
    print("Nature Machine Intelligence Article: main text target ~5,000 words,")
    print("excluding Methods, references and legends. Trim before submission.")
    todos = sum(
        1 for f in (HERE / "manuscript.md", HERE / "metadata.yaml", HERE / "refs.bib")
        for line in f.read_text().splitlines() if "TODO" in line or "VERIFY" in line
    )
    print(f"{todos} TODO/VERIFY markers outstanding across manuscript, metadata and refs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
