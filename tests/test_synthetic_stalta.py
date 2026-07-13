"""Tests for the Ridgecrest synthetic STA/LTA suite + detection_picks scorer."""

from __future__ import annotations

import pytest

from frugalmind import TaskKind
from frugalmind_suites.synthetic_stalta.items import SyntheticSTALTASuite
from frugalmind_suites.synthetic_stalta.scorers import (
    make_detection_picks_scorer,
    make_scorer_from_spec,
)


def test_detection_picks_matches_within_tolerance():
    scorer = make_detection_picks_scorer(tolerance_s=1.5)
    # exact
    assert scorer("[29.7]", [29.7]) == pytest.approx(1.0)
    # within tolerance
    assert scorer("[30.5]", [29.7]) == pytest.approx(1.0)
    # outside tolerance -> miss (F1 0)
    assert scorer("[40.0]", [29.7]) == 0.0


def test_detection_picks_negative_case_empty_is_perfect():
    scorer = make_detection_picks_scorer()
    # correct "no detection" on a negative case
    assert scorer("[]", []) == pytest.approx(1.0)
    assert scorer("No event detected.", []) == pytest.approx(1.0)
    # a false alarm on a negative case scores 0
    assert scorer("[15.0]", []) == 0.0


def test_detection_picks_two_events_f1():
    scorer = make_detection_picks_scorer(tolerance_s=1.5)
    # both found -> 1.0
    assert scorer("[29.7, 84.7]", [29.7, 84.7]) == pytest.approx(1.0)
    # one of two found -> P=1, R=0.5 -> F1=2/3
    assert scorer("[29.7]", [29.7, 84.7]) == pytest.approx(2 / 3)


def test_parse_prefers_json_array_over_prose():
    scorer = make_detection_picks_scorer()
    out = "After running STA/LTA the onset is at [29.8] seconds."
    assert scorer(out, [29.7]) == pytest.approx(1.0)


def test_spec_dispatch_and_unknown():
    scorer = make_scorer_from_spec(
        {"name": "detection_picks", "config": {"tolerance_s": 1.0}}
    )
    assert scorer("[29.7]", [29.7]) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="unknown scorer name"):
        make_scorer_from_spec({"name": "nope"})


def test_suite_loads_cases_and_scores_gold_perfectly():
    suite = SyntheticSTALTASuite(split="validation")
    rows = list(suite.export_rows())
    assert len(rows) >= 5
    n_pos = sum(1 for r in rows if r.metadata["expected_detection"])
    n_neg = len(rows) - n_pos
    assert n_pos >= 3 and n_neg >= 1  # positives + first-class negatives

    for r in rows:
        # The task is code-generation: the model writes the detector, the
        # sandbox runs it. (Asking an LLM to execute STA/LTA over ~1000 raw
        # samples in-context is unsolvable — a live 7B scored 0 on every item.)
        assert r.task_kind == TaskKind.CODE_GENERATION.value
        assert r.scorer_spec["name"] == "stalta_code"
        # The waveform travels in the spec so the row stays self-contained and
        # the sandbox can inject it; the prompt must NOT paste the samples.
        assert len(r.scorer_spec["config"]["waveform"]) > 100

    # A snippet that records the gold onsets scores each case perfectly.
    for prompt, gold, scorer in suite.items():
        import json

        snippet = f"```python\nrecord(picks={json.dumps(gold)})\n```"
        assert scorer(snippet, gold) == pytest.approx(1.0)
        # the prompt asks for code against pre-defined variables, not raw data
        assert "record(picks=" in prompt
        assert "waveform = [" not in prompt


def test_stalta_code_scorer_grades_a_real_detector():
    """A snippet that runs the detector but reports the raw (re-triggered)
    onsets must score below one that declusters the coda — the domain knowledge
    the eval is designed to reward."""
    suite = SyntheticSTALTASuite(split="validation")
    case = next(c for c in suite._cases() if c["expected_detection"])
    _, gold, spec, _ = suite._compose(case)
    scorer = make_scorer_from_spec(spec)

    naive = (
        "```python\n"
        "import numpy as np\n"
        "from obspy.signal.trigger import classic_sta_lta, trigger_onset\n"
        "cft = classic_sta_lta(np.array(waveform, float), int(1.0*fs), int(10.0*fs))\n"
        "record(picks=[float(o[0])/fs for o in trigger_onset(cft, 3.5, 1.5)])\n"
        "```"
    )
    exact = f"```python\nrecord(picks={gold})\n```"
    no_code = "I cannot run a detector on this."

    assert scorer(no_code, gold) == 0.0
    assert 0.0 < scorer(naive, gold) < scorer(exact, gold)
    assert scorer(exact, gold) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Hidden test split (anti-contamination)
# --------------------------------------------------------------------------- #
def test_committed_cases_are_public_validation_only():
    """The in-repo truth set must never contain test-split answers.

    A ranked score is computed on the hidden split; if its gold onsets were
    committed, the benchmark would measure memorisation, not capability.
    """
    import yaml

    from frugalmind_suites.synthetic_stalta import items as it

    doc = yaml.safe_load(it.CASES_PATH.read_text())
    for c in doc["cases"]:
        assert c["split"] == "validation", (
            f"case {c['id']!r} has split={c['split']!r} in the COMMITTED cases.yaml. "
            "Test-split answers must live only in the gated dataset "
            "(scripts/build_synthetic_stalta.py --split test)."
        )
        assert c["visibility"] == "public"


def test_test_split_requires_the_hidden_data(tmp_path, monkeypatch):
    """Asking for the test split without the pulled data fails loudly, with
    instructions — rather than silently scoring on the public split."""
    from frugalmind_suites.synthetic_stalta import items as it

    monkeypatch.setattr(it, "HIDDEN_CASES_PATH", tmp_path / "absent.yaml")
    # public split keeps working with no hidden data (the CI / fresh-clone case)
    assert len(it.SyntheticSTALTASuite(split="validation")._cases()) > 0
    with pytest.raises(FileNotFoundError, match="hidden test split is not available"):
        it.SyntheticSTALTASuite(split="test")._cases()
