from __future__ import annotations

import json

import pytest

import repere as F
from repere_suites import sta_lta as S
from repere_suites.sta_lta import scorers


def test_public_validation_split_loads():
    """What a fresh clone and a `pip install repere` actually see."""
    events = S.items._load_events(split="validation")
    assert len(events) == 2
    categories = {ev["category"] for ev in events}
    assert categories == {"regional_earthquake", "teleseism"}


def test_full_truth_set_covers_all_four_categories():
    """Negative-case discipline lives in the held-out partition.

    noise_day and quarry_blast are both held-out rows, so the public validation
    split is all-positive: a contributor developing against it never sees a
    case where the right answer is "no event". That is a gap in the public
    split, not a property of the benchmark -- see docs/holdout_policy.md on
    demoting burned rows to public validation rows.
    """
    if not S.items.HIDDEN_EVENTS_PATH.is_file():
        pytest.skip(f"held-out partition absent ({S.items.HIDDEN_EVENTS_PATH})")
    events = S.items._load_events()
    assert len(events) >= 6
    categories = {ev["category"] for ev in events}
    assert "regional_earthquake" in categories
    assert "teleseism" in categories
    assert "noise_day" in categories
    assert "quarry_blast" in categories


def test_each_suite_yields_one_item_per_event():
    n_events = len(S.items._load_events())
    for suite in S.ALL_SUITES:
        assert len(list(suite.items())) == n_events


def test_suite_task_kinds():
    expected = {
        S.STALTAIntentExtractionSuite: F.TaskKind.EXTRACTION,
        S.STALTAFetchCodeSuite: F.TaskKind.CODE_GENERATION,
        S.STALTATriggerCodeSuite: F.TaskKind.CODE_GENERATION,
        S.STALTAPlotSuite: F.TaskKind.PLOTTING,
        S.STALTAReportSuite: F.TaskKind.REPORT_DRAFTING,
    }
    for cls, kind in expected.items():
        assert cls.task_kind == kind


def test_json_scorer_tolerance_partial_credit_and_fences():
    scorer = scorers.make_json_extraction_scorer(
        required_fields=["network", "station", "channel", "starttime"],
        field_tolerances={"starttime": 5.0},
    )
    gold = {
        "network": "UW",
        "station": "LON",
        "channel": "BHZ",
        "starttime": "2001-02-28T18:54:30Z",
    }
    perfect = '{"network":"UW","station":"LON","channel":"BHZ","starttime":"2001-02-28T18:54:30Z"}'
    close = '{"network":"UW","station":"LON","channel":"BHZ","starttime":"2001-02-28T18:54:33Z"}'
    far = '{"network":"UW","station":"LON","channel":"BHZ","starttime":"2001-02-28T18:55:00Z"}'
    wrong_station = (
        '{"network":"UW","station":"PUPY","channel":"BHZ","starttime":"2001-02-28T18:54:30Z"}'
    )

    assert scorer(perfect, gold) == 1.0
    assert scorer(close, gold) == 1.0
    assert abs(scorer(far, gold) - 0.75) < 1e-9
    assert abs(scorer(wrong_station, gold) - 0.75) < 1e-9
    assert scorer("not json at all", gold) == 0.0
    assert scorer("", gold) == 0.0
    assert scorer("```json\n" + perfect + "\n```", gold) == 1.0


def test_report_scorer_positive_case():
    scorer = scorers.make_report_scorer(
        expected_detection=True,
        origin_time_iso="2001-02-28T18:54:32",
        origin_time_tolerance_s=60.0,
        magnitude=6.8,
        magnitude_tolerance=0.5,
    )
    good = "An earthquake was detected at station UW.LON near 2001-02-28T18:54:30 with an estimated M6.7 magnitude."
    no_time = "An earthquake was detected with M6.8 magnitude near LON station."
    silent = "Nothing happened."

    assert scorer(good, None) == 1.0
    assert abs(scorer(no_time, None) - 0.7) < 1e-9
    assert scorer(silent, None) == 0.0


def test_report_scorer_negative_case():
    scorer = scorers.make_report_scorer(
        expected_detection=False,
        required_terms=["no events"],
        forbidden_terms=["detected an earthquake", "tectonic event"],
    )
    correct = "STA/LTA produced no triggers; no events were observed during the window."
    hallucinated = (
        "STA/LTA detected an earthquake of magnitude 4.5 during an otherwise quiet window."
    )

    assert scorer(correct, None) == 1.0
    assert scorer(hallucinated, None) < 0.5


def test_suite_with_evalrunner_stub_adapter():
    registry = F.ModelRegistry()
    registry.register(
        F.ModelCard(
            id="stub-7b",
            family="qwen",
            size_b=7,
            context_window=32_000,
            backend="ollama",
            cost_per_1k_in=0.001,
            cost_per_1k_out=0.001,
        )
    )

    suite = S.STALTAIntentExtractionSuite()
    first_prompt, first_gold, _ = next(iter(suite.items()))
    perfect = json.dumps(first_gold)

    def factory(card):
        class Adapter:
            @property
            def card(self):
                return card

            def generate(self, prompt, **kw):
                text = perfect if prompt == first_prompt else "no idea"
                return F.Generation(
                    text=text,
                    prompt_tokens=10,
                    output_tokens=10,
                    latency_s=0.01,
                    cost_usd=0.001,
                    model_id=card.id,
                )

            def estimate_cost(self, *a, **kw):
                return 0.001

        return Adapter()

    runner = F.EvalRunner(
        registry=registry,
        suites=[suite],
        adapter_factory=factory,
        per_model_budget_usd=10.0,
        total_budget_usd=10.0,
    )
    [result] = runner.run_all()
    n_items = len(list(suite.items()))
    assert abs(result.score - (1.0 / n_items)) < 1e-9
    assert result.n_completed == n_items
