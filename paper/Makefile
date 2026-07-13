# Manuscript build — Nature Machine Intelligence
#
#   make          PDF + DOCX
#   make pdf      submission PDF (double-spaced, line-numbered)
#   make docx     Word, for co-author review / track changes
#   make figures  regenerate Fig. 1 from the live results
#   make check    what still blocks submission
#   make clean

PY := python

.PHONY: all pdf docx figures check clean

all:
	$(PY) build.py

pdf:
	$(PY) build.py --pdf

docx:
	$(PY) build.py --docx

# Fig. 1 is generated from site/data/skill_lift.json — the actual live results.
# Never hand-edit the figure; re-run the eval and rebuild.
figures:
	cd .. && pixi run -e full python scripts/make_paper_figure.py

check:
	@echo "── Outstanding TODO / VERIFY markers ─────────────────────────────"
	@grep -rn "TODO\|VERIFY" manuscript.md metadata.yaml refs.bib || echo "none"
	@echo
	@echo "── Blocking issues before submission ─────────────────────────────"
	@echo "  [ ] co-author names, affiliations, ORCIDs, contribution sentences"
	@echo "  [ ] EVERY reference verified against the real publication (DOIs resolve)"
	@echo "  [ ] AstaBench / Inspect / contamination refs added"
	@echo "  [ ] repeated runs with 95% CIs (local models cost \$$0 to re-run)"
	@echo "  [ ] >=1 eval from a second family, or drop the 3-family claim"
	@echo "  [ ] head-to-head against an existing benchmark"
	@echo "  [ ] Zenodo DOIs minted for code + data"
	@echo "  [ ] main text trimmed to ~5,000 words (excl. Methods/refs/legends)"

clean:
	rm -rf build
