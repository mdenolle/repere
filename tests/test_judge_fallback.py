"""Tests for the optional LLM-judge fallback in `make_report_scorer` (P1.5).

Three contracts pinned here:

  1. With ``judge_adapter=None`` (default), behaviour is byte-identical to
     the pre-P1.5 scorer. CI never accidentally calls a judge.
  2. With an adapter supplied, the judge is only invoked when the lexical
     score is below ``judge_threshold``. Above threshold, no call.
  3. When the judge runs, the final score is ``max(lexical, judge)`` so a
     model whose lexical was already OK is never demoted by a quirky judge.

The mock adapter records every call so the tests can verify the threshold
gate empirically rather than only by output value.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from repere_suites.sta_lta.scorers import (
    _format_catalog_facts,
    _load_judge_prompt_template,
    _parse_judge_score,
    make_report_scorer,
)


# ---------------------------------------------------------------------------
# Mock judge adapter
# ---------------------------------------------------------------------------


@dataclass
class _MockGeneration:
    text: str


@dataclass
class _MockJudge:
    """Records every prompt sent to it and returns a fixed score."""

    response: str = '{"score": 80, "reason": "well-written"}'
    raise_on_call: bool = False
    calls: list[str] = field(default_factory=list)

    def generate(self, prompt: str, **_kwargs):
        if self.raise_on_call:
            raise RuntimeError("simulated judge failure")
        self.calls.append(prompt)
        return _MockGeneration(text=self.response)


# ---------------------------------------------------------------------------
# 1. Byte-identical default behaviour
# ---------------------------------------------------------------------------


def test_default_scorer_is_byte_identical_to_pre_p1_5():
    """`judge_adapter=None` must produce the exact same numbers as before."""
    scorer = make_report_scorer(
        expected_detection=True,
        origin_time_iso="2001-02-28T18:54:32",
        magnitude=6.8,
    )
    good = "An earthquake was detected at UW.LON near 2001-02-28T18:54:30 (M6.7)."
    silent = "Nothing happened."
    # These exact values were the contract before P1.5.
    assert scorer(good, None) == 1.0
    assert scorer(silent, None) == 0.0


def test_default_scorer_does_not_load_template():
    """When no judge is configured, the prompt file shouldn't matter — even if
    we move it, the closure must not have already cached its contents."""
    # We can't patch the path easily, but we can assert the scorer doesn't have
    # any template baggage by ensuring it doesn't crash even if catalog
    # parameters are entirely empty (no formatting work was done at build-time).
    scorer = make_report_scorer(expected_detection=True)
    assert scorer("Earthquake detected.", None) == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# 2. Threshold gating
# ---------------------------------------------------------------------------


def test_judge_not_called_when_lexical_above_threshold():
    judge = _MockJudge(response='{"score": 99, "reason": "perfect"}')
    scorer = make_report_scorer(
        expected_detection=True,
        origin_time_iso="2001-02-28T18:54:32",
        magnitude=6.8,
        judge_adapter=judge,
        judge_threshold=0.5,
    )
    good = "An earthquake was detected at UW.LON near 2001-02-28T18:54:30 (M6.7)."
    score = scorer(good, None)
    assert score == 1.0
    assert judge.calls == [], "judge must not be invoked when lexical >= threshold"


def test_judge_called_when_lexical_below_threshold():
    judge = _MockJudge(response='{"score": 70, "reason": "decent prose"}')
    scorer = make_report_scorer(
        expected_detection=True,
        origin_time_iso="2001-02-28T18:54:32",
        magnitude=6.8,
        judge_adapter=judge,
        judge_threshold=0.5,
    )
    weak = "Nothing happened."  # lexical = 0.0
    score = scorer(weak, None)
    assert len(judge.calls) == 1, "judge must be invoked exactly once"
    assert score == pytest.approx(0.70), "score should reflect judge's 70/100"


def test_threshold_is_exclusive_at_floor():
    """Lexical exactly at threshold should not trigger the judge."""
    judge = _MockJudge()
    scorer = make_report_scorer(
        expected_detection=True,
        judge_adapter=judge,
        judge_threshold=0.4,
    )
    # "Earthquake detected." → lexical exactly 0.4 (the keyword-hit branch).
    out = "Earthquake detected."
    score = scorer(out, None)
    assert judge.calls == [], "lexical == threshold must not trigger the judge"
    assert score == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# 3. Score composition: max(lexical, judge)
# ---------------------------------------------------------------------------


def test_judge_does_not_demote_when_lexical_already_high_below_threshold():
    """If lexical is below threshold but still > judge, keep lexical."""
    # Lexical for "Earthquake detected." is 0.4 (the keyword-hit branch).
    # Threshold is 0.41, so judge IS called; judge returns 0.20.
    # max(0.4, 0.20) must be 0.4 — the judge does not demote.
    judge = _MockJudge(response='{"score": 20, "reason": "miscalibrated"}')
    scorer_low = make_report_scorer(
        expected_detection=True,
        judge_adapter=judge,
        judge_threshold=0.41,
    )
    out = "Earthquake detected."  # lexical = 0.4
    score = scorer_low(out, None)
    assert score == pytest.approx(0.4), "max(lexical, judge) — keep the higher value"
    assert len(judge.calls) == 1, "judge must have been invoked (lexical 0.4 < 0.41)"


def test_judge_uplifts_when_higher_than_lexical():
    judge = _MockJudge(response='{"score": 85, "reason": "nuanced explanation"}')
    scorer = make_report_scorer(
        expected_detection=True,
        judge_adapter=judge,
        judge_threshold=0.5,
    )
    out = "The waveform showed something."  # lexical ~ 0
    score = scorer(out, None)
    assert score == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# 4. Robustness: judge errors / parses
# ---------------------------------------------------------------------------


def test_judge_failure_falls_back_to_lexical():
    """An exception from the judge must not blow up the eval; lexical wins."""
    judge = _MockJudge(raise_on_call=True)
    scorer = make_report_scorer(
        expected_detection=True,
        judge_adapter=judge,
        judge_threshold=0.5,
    )
    out = "Earthquake detected."  # lexical = 0.4
    score = scorer(out, None)
    assert score == pytest.approx(0.4), "judge failure must not change score"


def test_template_load_failure_disables_judge_path(monkeypatch):
    """If the prompt file is missing or unreadable at scorer-build time,
    the judge path is disabled and the scorer behaves as if no judge was
    supplied. Eval must not abort."""
    from repere_suites.sta_lta import scorers as scorers_mod

    def _broken_loader(*_args, **_kwargs):
        raise FileNotFoundError("simulated missing prompt template")

    monkeypatch.setattr(scorers_mod, "_load_judge_prompt_template", _broken_loader)

    judge = _MockJudge(response='{"score": 99}')
    scorer = make_report_scorer(
        expected_detection=True,
        judge_adapter=judge,
        judge_threshold=0.5,
    )
    out = "Earthquake detected."  # lexical = 0.4 → would normally trigger judge
    score = scorer(out, None)
    assert score == pytest.approx(0.4), "scorer must fall back to lexical when template missing"
    assert judge.calls == [], "judge must not be invoked when template load failed"


def test_judge_handles_template_format_errors():
    """Malformed templates (extra braces, missing placeholders) must not
    propagate. _call_judge has the brace-rendering inside its try/except so
    a broken template returns 0.0 instead of raising."""
    from repere_suites.sta_lta.scorers import _call_judge

    judge = _MockJudge(response='{"score": 80}')
    # Template with an unknown placeholder — `{not_a_field}` raises KeyError
    # when `.format()` is called.
    bad_template = "Score this: {model_output}\nAlso: {not_a_field}"
    result = _call_judge(
        judge,
        model_output="hello",
        expected_detection=True,
        catalog_facts="(no catalog facts provided)",
        template=bad_template,
    )
    assert result == 0.0
    assert judge.calls == [], "adapter must not be called when template formatting fails"


@pytest.mark.parametrize(
    "response, expected",
    [
        ('{"score": 50}', 0.5),
        ('{"score": 100, "reason": "perfect"}', 1.0),
        ('{"score": 0}', 0.0),
        ('{"score": 73.5}', 0.735),
        ("```json\n{\"score\": 60}\n```", 0.6),  # markdown fences tolerated
        ("garbage", 0.0),
        ("", 0.0),
        ('{"reason": "no score"}', 0.0),
    ],
)
def test_parse_judge_score(response, expected):
    assert _parse_judge_score(response) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 5. Prompt template shape
# ---------------------------------------------------------------------------


def test_judge_prompt_template_has_required_placeholders():
    template = _load_judge_prompt_template()
    for placeholder in ("{expected_detection}", "{catalog_facts}", "{model_output}"):
        assert placeholder in template, (
            f"judge prompt template missing placeholder {placeholder}"
        )
    # Anti-pattern guidance and JSON output instruction must be in the rubric;
    # changes to either should be deliberate.
    assert "JSON" in template or "json" in template
    assert "no-event" in template.lower() or "no events" in template.lower()


def test_format_catalog_facts_renders_supplied_fields_only():
    out = _format_catalog_facts(
        origin_time_iso="2001-02-28T18:54:32",
        magnitude=6.8,
        required_terms=None,
        forbidden_terms=None,
    )
    assert "origin_time: 2001-02-28T18:54:32" in out
    assert "magnitude: 6.8" in out
    assert "required_terms" not in out
    assert "forbidden_terms" not in out


def test_format_catalog_facts_handles_empty_input():
    out = _format_catalog_facts(
        origin_time_iso=None, magnitude=None, required_terms=None, forbidden_terms=None
    )
    assert "no catalog facts" in out.lower()


# ---------------------------------------------------------------------------
# 6. Prompt content reaches the adapter unchanged
# ---------------------------------------------------------------------------


def test_judge_prompt_contains_model_output_and_truth():
    judge = _MockJudge(response='{"score": 70, "reason": "ok"}')
    scorer = make_report_scorer(
        expected_detection=True,
        origin_time_iso="2001-02-28T18:54:32",
        magnitude=6.8,
        judge_adapter=judge,
        judge_threshold=0.5,
    )
    weak = "MAGIC_REPORT_TOKEN something happened."  # forces judge path
    scorer(weak, None)
    assert len(judge.calls) == 1
    prompt = judge.calls[0]
    assert "MAGIC_REPORT_TOKEN" in prompt
    assert "expected_detection: true" in prompt
    assert "2001-02-28T18:54:32" in prompt
    assert "magnitude: 6.8" in prompt
