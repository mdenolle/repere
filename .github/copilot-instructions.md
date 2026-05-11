# Copilot review instructions for FrugalMind

These instructions tell GitHub Copilot's PR reviewer what matters in this
repo and what doesn't. They exist because nine rounds of review feedback
across Phase 1 and Phase 2 surfaced a clear pattern of high-signal catches
(blocking I/O in async, drift after field additions, broken CLI examples
in docs) and low-signal noise (linter-level nits, restating what code
does, suggesting rewrites that erase deliberate patterns).

Treat this file as the rubric. If a comment doesn't fit one of the
review priorities below, don't post it.

## Review priorities (ranked)

1. **Correctness and concurrency.** Bugs, race conditions, blocking work
   inside `async def` functions, dead conditionals, off-by-one in
   slicing/zipping, mutable default arguments.
2. **Cross-file drift.** When a new field, value, or enum is added —
   `openness`, `toolset`, `cutoff_date`, `split`, `visibility`, a new
   tool name, a new skill — every site of use (dataclass, YAML, exporter,
   site renderer, fixtures, tests) must be updated. Flag any
   half-applied addition.
3. **Documentation that misrepresents the code.** CLI examples,
   docstrings, README snippets, and ROADMAP/CHANGELOG entries must
   resolve from the repo root and match the actual behaviour. A wrong
   path in a docstring is a real bug here — users copy-paste them.
4. **Test coverage of new behavioural branches.** If a public function
   gains a parameter, a new branch, or a new failure mode, the test
   file should exercise it. Flag uncovered new branches; don't flag
   coverage of unchanged code.
5. **Optional-extras gating.** This repo has `[eval]`, `[geo]`, `[plot]`,
   `[dev]`, `[test]` extras. Any code that imports `inspect_ai`,
   `obspy`, `matplotlib`, `scikit-image`, `numpy` must do so lazily
   (inside a function body) or be gated behind an `importorskip` in
   tests. Conversely, **don't** suggest "simplifying" lazy imports back
   to module top — they're deliberate.
6. **Frugality framing.** FrugalMind's thesis is cost-vs-quality. Don't
   suggest changes that add a model call, a tool call, or a network
   round-trip without justifying it against the cost-Pareto framing.

## Specific things to flag

These have all bitten us; encode them so we don't repeat:

- **Blocking I/O inside `async def`.** Any `subprocess.run(...)`,
  `requests.get(...)`, `obspy.Client(...).get_waveforms(...)`, file
  I/O, or third-party sync API call inside an `async` function must be
  wrapped in `asyncio.to_thread(...)` (or equivalent) so it doesn't
  stall Inspect's event loop.
- **`pytest.importorskip("inspect_ai")` at module level.** This skips
  the entire test module when the extra is missing — including tests
  that don't need it. Split such tests into a separate file (see
  `tests/test_react_descriptor.py` vs `tests/test_react_agent.py` for
  the pattern). Same rule for `obspy`, `matplotlib`.
- **Always-truthy conditionals.** `if x is not None or "string literal":`
  and similar patterns where one operand is always truthy. Ruff doesn't
  catch all of these; you should.
- **Eager imports of optional deps at module top.** Move into the
  function body. The package must remain importable without `[eval]`,
  `[geo]`, `[plot]`.
- **Stale paths in docstrings.** Especially `inspect eval --solver`
  examples — verify the path resolves from the repo root.
- **Half-applied schema changes.** If `events.yaml` gains a field, check
  that `_load_events`, the suite fixtures, the JSONL exporter, the
  drift tests, and the prompt templates all see it.
- **Unused locals, unused imports, unused noqa.** Ruff catches most;
  flag what it misses.
- **`# noqa: …`** on a line where the cited rule no longer fires.

## Specific things to skip

These add noise and burn review attention:

- **Style preferences ruff handles.** Import order, blank-line counts,
  E501 line length, unused imports of types ruff already flags. The
  ruleset is E, F, I, B, UP — assume those will be enforced in CI.
- **Restating what a function or test does.** The PR diff already shows
  the code; a paraphrase isn't review.
- **Suggesting docstring format changes.** Docstrings here are prose;
  no Sphinx/NumPy/Google convention is enforced.
- **Asking for more tests when coverage is already strong.** Look at
  the existing tests for the modified module before suggesting more.
- **Suggesting "cleaner" rewrites of deliberate patterns.** Examples:
  the lazy-import pattern for optional deps; the
  `_compose(ev) -> (prompt, gold, scorer_spec, meta)` shared helper
  between `items()` and `export_rows()`; the `make_*_scorer(...)`
  factory pattern; the parametric truth set in `events.yaml`.

## Project-specific framing rules

- **Negative-case discipline is real.** No-event windows are first-class
  items. Reporting zero detections on a quiet day is a correct answer,
  not a bug. Don't suggest "improvements" that would make the agent
  hallucinate a detection on a negative case.
- **Stacked PRs are a deliberate workflow.** Branches like
  `p2-4-react-baseline` are based on still-in-review parent branches
  (e.g., `p2-1-inspect-substrate`). Don't suggest changing the base
  branch or rebasing strategy — just review the diff in front of you.
- **The roadmap is the source of truth.** Every PR should link to a
  `ROADMAP.md` item (P1.x, P2.x, P3.x). If a PR doesn't, flag it
  once — but don't repeat the comment.
- **AstaBench alignment is a goal, not a constraint.** It's fine to
  diverge from AstaBench's conventions when there's a reason; the
  rationale should appear in the PR description. Don't reflexively
  flag divergences.

## Tone

Be terse. One sentence per comment is usually enough. Concrete
suggestions ("wrap in `asyncio.to_thread`") beat abstract ones
("consider concurrency"). Cite a file and line; don't generalise.

If you're unsure whether something is a substantive issue or a style
preference, skip it. False positives cost more attention than false
negatives in this codebase.
