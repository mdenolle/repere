# Manuscript — Nature Machine Intelligence (Article)

Write in Markdown; build to a Nature-formatted PDF and a Word document.

```bash
cd paper
make          # PDF + DOCX  ->  build/
make check    # what still blocks submission
```

## Files

| File | Role |
|---|---|
| `manuscript.md` | **the prose.** Abstract → Main → Results → Discussion → Methods → Figures → Tables |
| `metadata.yaml` | **the author list** and the mandatory Nature statements. Add co-authors here, nowhere else. |
| `refs.bib` | bibliography. **Every entry must be verified before submission.** |
| `csl/nature.csl` | Nature citation style (superscript numeric) |
| `build.py` | assembles title block + back matter and drives pandoc |
| `figures/` | Fig. 1, generated from the live results — never hand-edited |

## Why this builds a plain double-spaced PDF and not a Nature template

Nature Portfolio does **not** require its own LaTeX/Word template at initial
submission. It asks for a readable, double-spaced, line-numbered manuscript with
figures and legends. That is exactly what `make pdf` produces. Strict styling is
applied at acceptance, by the publisher.

## Adding a co-author

Edit `metadata.yaml` only:

```yaml
author:
  - name: Jane Doe
    orcid: 0000-0000-0000-0000
    affiliation: [2]          # index into `affiliations` below
affiliations:
  - id: 2
    name: Department of X, University of Y, City, Country
```

Then add **one specific sentence** for them under `author-contributions`. Nature
requires specificity — *"contributed to the project"* is not acceptable and is a
common cause of editorial queries. Say what they actually did: which eval they
built, which analysis they ran, which section they wrote.

## Article structure (Nature Article)

Nature Articles put the *what we found* in **Results** and the *how* in
**Methods**, which sits after the Discussion and is not counted against the main
word limit. Main text targets ~5,000 words excluding Methods, references and
legends; up to ~8 display items.

## Honest status

The framework (the contribution) is written. The **evidence is not yet at
Article strength**, and `make check` lists exactly what is missing. The two
largest gaps, both of which a reviewer will raise immediately:

1. **Two evaluations, both from one of three proposed families.** The taxonomy is
   currently *proposed*, not *demonstrated*. One eval from the document-based or
   research-workflow family fixes this.
2. **Single run, no confidence intervals.** The local models cost \$0 to re-run;
   there is no defensible reason to submit point estimates.

The manuscript is written so these slots are visible rather than hidden. Fill
them before submitting, or the reviews will fill them for you.
