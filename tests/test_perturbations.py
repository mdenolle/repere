"""Tests for `repere.perturbations`.

The contract, in the order it matters:

  1. **Meaning is preserved.** A structural perturbation that changes what the
     data says is a different task, not a robustness test. This is where the
     geophysics gets decided, so it is tested first.
  2. **Everything is reproducible.** A perturbed run that cannot be repeated is
     an anecdote. Same seed, same faults, same paraphrases.
  3. Injected faults are distinguishable from real agent bugs.
"""

from __future__ import annotations

import asyncio

import pytest

from repere.perturbations import (
    DEFAULT_FAULT_RATE,
    FAULTS,
    STRUCTURAL_TRANSFORMS,
    FaultInjector,
    InjectedFault,
    paraphrases,
    perturb_structurally,
    phase_metadata,
    summarise_injections,
    wrap_callable,
)

REQUEST = {
    "network": "UW",
    "station": "LON",
    "location": "",
    "channel": "BHZ",
    "starttime": "2001-02-28T18:54:25Z",
    "sampling_rate": 40,
}


# ---------------------------------------------------------------------------
# 1. Meaning preservation
# ---------------------------------------------------------------------------


def test_an_empty_location_code_may_be_respelled_but_the_channel_may_not():
    """`""` and `--` are the same location. `BHZ` and `HHZ` are not the same channel.

    This is the line the whole structural phase rests on. An empty location code
    has three spellings in the wild and clients disagree about which to send, so
    respelling it is a fair test of robustness. Channel codes encode band and
    sample rate: BHZ is broadband, HHZ is high-rate. An agent that answered
    differently after a channel swap would be *correct* to do so, which makes
    the swap a different task rather than a perturbation.
    """
    out = perturb_structurally(REQUEST, transforms=["location_dashes"])
    assert out["location"] == "--"
    assert out["channel"] == "BHZ", "the channel must survive untouched"

    # And no transform in the catalogue touches a channel code.
    for name, fn in STRUCTURAL_TRANSFORMS.items():
        assert fn(dict(REQUEST))["channel"] == "BHZ", f"{name} altered the channel"


def test_time_reshapes_keep_the_same_instant():
    epoch = perturb_structurally(REQUEST, transforms=["time_epoch"])["starttime"]
    slashed = perturb_structurally(REQUEST, transforms=["time_slashed"])["starttime"]
    assert epoch == pytest.approx(983386465.0)  # 2001-02-28T18:54:25Z
    assert slashed == "2001/02/28 18:54:25"


def test_seed_id_shape_keeps_all_four_components():
    out = perturb_structurally("UW.LON..BHZ", transforms=["seed_id_dict"])
    assert out == {"network": "UW", "station": "LON", "location": "", "channel": "BHZ"}


def test_key_renaming_and_reordering_preserve_the_mapping():
    renamed = perturb_structurally(REQUEST, transforms=["key_naming"])
    assert renamed["start_time"] == REQUEST["starttime"]
    assert "starttime" not in renamed

    reordered = perturb_structurally(REQUEST, transforms=["key_order"])
    assert reordered == REQUEST  # equal as mappings
    assert list(reordered) != list(REQUEST)  # different insertion order


def test_numeric_type_change_keeps_the_value():
    out = perturb_structurally(REQUEST, transforms=["numeric_type"])
    assert out["sampling_rate"] == 40
    assert isinstance(out["sampling_rate"], float)


def test_an_unknown_transform_raises_rather_than_weakening_the_phase():
    with pytest.raises(ValueError, match="unknown structural transform"):
        perturb_structurally(REQUEST, transforms=["channel_swap"])


# ---------------------------------------------------------------------------
# 2. Reproducibility
# ---------------------------------------------------------------------------


def test_the_same_seed_injects_the_same_faults():
    a = FaultInjector(rate=0.5, seed=7)
    b = FaultInjector(rate=0.5, seed=7)
    seq_a = [(f.name if (f := a.next_fault("fdsn_get_waveforms")) else None) for _ in range(40)]
    seq_b = [(f.name if (f := b.next_fault("fdsn_get_waveforms")) else None) for _ in range(40)]
    assert seq_a == seq_b
    assert any(seq_a), "a rate of 0.5 over 40 calls must fire at least once"


def test_a_different_seed_injects_a_different_pattern():
    a = FaultInjector(rate=0.5, seed=1)
    b = FaultInjector(rate=0.5, seed=2)
    seq_a = [(f.name if (f := a.next_fault("t")) else None) for _ in range(40)]
    seq_b = [(f.name if (f := b.next_fault("t")) else None) for _ in range(40)]
    assert seq_a != seq_b


def test_the_observed_rate_tracks_the_configured_rate():
    inj = FaultInjector(rate=DEFAULT_FAULT_RATE, seed=0)
    fired = sum(1 for _ in range(2000) if inj.next_fault("t") is not None)
    assert 0.17 < fired / 2000 < 0.23


def test_rate_zero_never_fires_and_rate_one_always_does():
    assert FaultInjector(rate=0.0, seed=0).next_fault("t") is None
    assert FaultInjector(rate=1.0, seed=0).next_fault("t") is not None


def test_an_invalid_rate_raises():
    with pytest.raises(ValueError, match="fault rate"):
        FaultInjector(rate=1.5)


def test_paraphrases_are_deterministic_and_keep_the_original_first():
    a = paraphrases("Compute the dv/v series.", j=5, seed=3)
    b = paraphrases("Compute the dv/v series.", j=5, seed=3)
    assert a == b
    assert a[0] == "Compute the dv/v series."
    assert len(a) == 5 and len(set(a)) == 5


def test_authored_paraphrases_win_over_the_rules():
    got = paraphrases(
        "Compute the dv/v series.",
        j=3,
        authored={"item-1": ["Work out the velocity change.", "Give me dv/v over time."]},
        item_id="item-1",
    )
    assert got == [
        "Compute the dv/v series.",
        "Work out the velocity change.",
        "Give me dv/v over time.",
    ]


# ---------------------------------------------------------------------------
# 3. Injected faults are distinguishable, and behave as described
# ---------------------------------------------------------------------------


def test_an_injected_fault_has_its_own_type_and_names_itself():
    inj = FaultInjector(rate=1.0, seed=0, faults=(FAULTS[0],))

    def tool():
        return "never reached"

    wrapped = wrap_callable(tool, "fdsn_get_waveforms", inj)
    with pytest.raises(InjectedFault) as exc:
        wrapped()
    assert exc.value.fault_name == "fdsn_503"
    assert "503" in str(exc.value)


def test_a_degrading_fault_returns_something_that_looks_usable():
    """The hard case: no exception, a well-formed response, and less data."""
    empty = next(f for f in FAULTS if f.name == "empty_stream")
    inj = FaultInjector(rate=1.0, seed=0, faults=(empty,))
    wrapped = wrap_callable(lambda: {"records": [1, 2, 3]}, "m2m", inj)
    assert wrapped() == {"records": []}


def test_a_partial_return_drops_records_without_erroring():
    partial = next(f for f in FAULTS if f.name == "m2m_partial")
    inj = FaultInjector(rate=1.0, seed=0, faults=(partial,))
    wrapped = wrap_callable(lambda: {"records": [1, 2, 3, 4]}, "m2m", inj)
    assert wrapped() == {"records": [1, 2]}


def test_a_truncated_stream_is_short_not_empty():
    trunc = next(f for f in FAULTS if f.name == "truncated_miniseed")
    inj = FaultInjector(rate=1.0, seed=0, faults=(trunc,))
    wrapped = wrap_callable(lambda: b"x" * 100, "fdsn", inj)
    out = wrapped()
    assert 0 < len(out) < 100


def test_async_tools_are_wrapped_too():
    inj = FaultInjector(rate=1.0, seed=0, faults=(FAULTS[0],))

    async def tool():
        return "ok"

    wrapped = wrap_callable(tool, "fdsn", inj)
    with pytest.raises(InjectedFault):
        asyncio.run(wrapped())


def test_a_clean_call_passes_through_untouched():
    inj = FaultInjector(rate=0.0, seed=0)
    wrapped = wrap_callable(lambda: {"records": [1, 2, 3]}, "m2m", inj)
    assert wrapped() == {"records": [1, 2, 3]}


def test_the_injection_log_records_what_fired():
    inj = FaultInjector(rate=1.0, seed=0)
    for _ in range(20):
        try:
            wrap_callable(lambda: {"records": [1, 2]}, "t", inj)()
        except InjectedFault:
            pass
    counts = summarise_injections(inj)
    assert sum(counts.values()) == 20
    assert set(counts) <= {f.name for f in FAULTS}


# ---------------------------------------------------------------------------
# 4. Phase provenance
# ---------------------------------------------------------------------------


def test_phase_metadata_carries_what_a_row_needs():
    assert phase_metadata("baseline", seed=3) == {"phase": "baseline", "perturbation_seed": 3}
    fault = phase_metadata("fault", seed=3)
    assert fault["fault_rate"] == DEFAULT_FAULT_RATE
    assert phase_metadata("fault", seed=3, rate=0.5)["fault_rate"] == 0.5


def test_an_unknown_phase_raises():
    with pytest.raises(ValueError, match="unknown phase"):
        phase_metadata("chaos", seed=0)
