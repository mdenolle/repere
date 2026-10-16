"""The glossary must name every field and metric the code produces.

This guard exists because the drift it prevents already happened once, inside a
single working session: `docs/glossary.md` was written first, then
`repere.reliability` and leaderboard schema v0.2 added sixteen reliability
fields and eleven row fields that the glossary did not mention. A glossary that
silently falls behind the code is worse than no glossary, because a reader
believes it.

The check is deliberately shallow — the term appears somewhere in the file — so
it cannot tell a good definition from a bad one. It can only tell a *missing*
one, which is the failure mode that actually occurs.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from repere.leaderboard import LeaderboardRow, ReliabilityBlock
from repere.reliability import __all__ as RELIABILITY_FUNCTIONS

GLOSSARY = Path(__file__).resolve().parents[1] / "docs" / "glossary.md"

# Fields whose name is structural rather than a term a reader would look up.
_STRUCTURAL = {"rank", "model_id", "suite", "run_file", "n_completed", "n_total", "reliability"}


@pytest.fixture(scope="module")
def glossary_text() -> str:
    assert GLOSSARY.exists(), f"{GLOSSARY} is missing"
    return GLOSSARY.read_text()


@pytest.mark.parametrize(
    "field_name",
    sorted({f.name for f in fields(LeaderboardRow)} - _STRUCTURAL),
)
def test_every_leaderboard_field_is_in_the_glossary(field_name, glossary_text):
    assert field_name in glossary_text, (
        f"leaderboard row field {field_name!r} is not named in docs/glossary.md. "
        "Add it in the same commit that added the field."
    )


@pytest.mark.parametrize("field_name", sorted(f.name for f in fields(ReliabilityBlock)))
def test_every_reliability_field_is_in_the_glossary(field_name, glossary_text):
    assert field_name in glossary_text, (
        f"reliability field {field_name!r} is not named in docs/glossary.md."
    )


@pytest.mark.parametrize("fn_name", sorted(RELIABILITY_FUNCTIONS))
def test_every_reliability_function_is_in_the_glossary(fn_name, glossary_text):
    assert fn_name in glossary_text, (
        f"reliability function {fn_name!r} is not named in docs/glossary.md."
    )


def test_retired_fields_are_documented_as_retired():
    """Removing a field is a vocabulary change too, and readers need the note."""
    text = GLOSSARY.read_text()
    for retired in ("efficiency_score", "quality_percent"):
        assert retired in text, f"{retired} was retired but is not explained"
    section = text[text.index("Retired in v0.2") :]
    assert "efficiency_score" in section
    assert "quality_percent" in section


def test_the_scorer_spec_names_are_all_listed(glossary_text):
    """Every `{"name": ...}` a suite row can carry must be findable."""
    for name in (
        "json_extraction",
        "code_execution",
        "plot_ssim",
        "report",
        "retrieval_metrics",
        "term_preservation",
        "citation_support",
        "numerical_regression",
        "stalta_code",
        "detection_picks",
        "trajectory_dag",
        "trajectory_policy",
        "dvv_recovery",
        "dvv_series_regression",
        "jev_grounding",
        "jev_claimed_vs_actual",
    ):
        assert name in glossary_text, f"scorer name {name!r} missing from the glossary"
