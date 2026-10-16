"""Degrading the environment on purpose, to measure what survives it.

Robustness is the reliability dimension that needs more than repeats: it needs
the *same* task run against a worse world. Three kinds, matching the three
phases in ``repere.reliability.robustness_ratio``:

``fault``
    The data service misbehaves. Not a synthetic abstraction — every fault here
    is one an FDSN or OOI M2M client meets in a normal week.

``structural``
    The interface is reshaped without changing what it means. Epoch seconds
    instead of ISO-8601, ``--`` instead of ``""`` for an empty location code,
    a SEED id as a dict instead of a dotted string.

``prompt``
    The same request, asked differently.

**Meaning-preserving is a strict requirement, and geophysics is where it gets
decided.** Renaming ``BHZ`` to ``HHZ`` is *not* a structural perturbation: those
are different channels at different sample rates, and an agent that noticed the
difference would be right to change its answer. The perturbations below change
only spelling, shape, units-with-conversion, and ordering. If a domain expert
would answer differently after the perturbation, it is a different task, not a
robustness test.

Everything here is seeded and reproducible. A perturbed run that cannot be
repeated is an anecdote, so every injected fault is a deterministic function of
``(seed, tool_name, call_index)`` and every row records ``perturbation_seed``.

The core takes plain values and plain callables, so it is testable without
``inspect_ai`` installed. :func:`wrap_registry_tools` is the thin adapter that
applies it to the real tool surface.
"""

from __future__ import annotations

import json
import random
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "DEFAULT_FAULT_RATE",
    "FAULTS",
    "STRUCTURAL_TRANSFORMS",
    "FaultInjector",
    "InjectedFault",
    "ToolFault",
    "paraphrases",
    "perturb_structurally",
    "wrap_callable",
]

# The reliability literature's default, adopted unchanged so our numbers are
# comparable to the published ones. See docs/ecosystem/hal_adoption.md.
DEFAULT_FAULT_RATE = 0.2


class InjectedFault(RuntimeError):
    """Raised inside a wrapped tool to simulate a service failure.

    A distinct type so a scorer can tell an injected fault from a real bug in
    the agent's code. An agent that crashes *because we broke the service* has
    not failed the task in the same way as one that wrote a broken detector.
    """

    def __init__(self, fault_name: str, message: str):
        super().__init__(message)
        self.fault_name = fault_name


@dataclass(frozen=True)
class ToolFault:
    """One way a data service can misbehave.

    ``raises`` faults interrupt the call; ``returns`` faults hand back a
    degraded but structurally valid result, which is the harder case — the agent
    gets something that looks usable and is not.
    """

    name: str
    description: str
    raises: bool = True
    message: str = ""
    degrade: Callable[[Any], Any] | None = None


def _truncate_bytes(value: Any) -> Any:
    """Return the first 60% of a byte payload: a short read, not a failed one."""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value[: max(1, int(len(value) * 0.6))])
    if isinstance(value, str):
        return value[: max(1, int(len(value) * 0.6))]
    return value


def _drop_records(value: Any) -> Any:
    """Return roughly half the records of a list-shaped response."""
    if isinstance(value, list):
        return value[: len(value) // 2]
    if isinstance(value, dict):
        for key in ("records", "traces", "items", "data"):
            if isinstance(value.get(key), list):
                out = dict(value)
                out[key] = value[key][: len(value[key]) // 2]
                return out
    return value


def _empty_result(value: Any) -> Any:
    """A valid, well-formed, empty response. No error, no data."""
    if isinstance(value, list):
        return []
    if isinstance(value, dict):
        out = dict(value)
        for key in ("records", "traces", "items", "data"):
            if key in out:
                out[key] = []
        return out
    if isinstance(value, (bytes, bytearray)):
        return b""
    return value


# The catalogue. Every one of these is a failure an FDSN or OOI M2M client
# actually meets; none is invented for the sake of having a fault.
FAULTS: tuple[ToolFault, ...] = (
    ToolFault(
        "fdsn_503",
        "The FDSN dataselect service returns 503 Service Unavailable.",
        message="HTTP 503 from FDSN dataselect: service temporarily unavailable",
    ),
    ToolFault(
        "fdsn_timeout",
        "The request exceeds the client timeout with no response.",
        message="read timed out after 30s waiting for FDSN dataselect",
    ),
    ToolFault(
        "m2m_auth",
        "OOI M2M rejects the credentials mid-session.",
        message="HTTP 401 from OOI M2M: invalid or expired API credentials",
    ),
    ToolFault(
        "m2m_partial",
        "M2M returns a valid response holding only part of the requested span.",
        raises=False,
        degrade=_drop_records,
    ),
    ToolFault(
        "truncated_miniseed",
        "The byte stream ends mid-record; the last block is unreadable.",
        raises=False,
        degrade=_truncate_bytes,
    ),
    ToolFault(
        "empty_stream",
        "A well-formed response containing no traces at all.",
        raises=False,
        degrade=_empty_result,
    ),
)

_FAULTS_BY_NAME = {f.name: f for f in FAULTS}


@dataclass
class FaultInjector:
    """Decides, reproducibly, whether a given tool call fails and how.

    The decision is a pure function of ``(seed, tool_name, call_index)``, so two
    runs with the same seed inject the same faults at the same points. Without
    that, a robustness number is not a measurement of the agent.
    """

    rate: float = DEFAULT_FAULT_RATE
    seed: int = 0
    faults: tuple[ToolFault, ...] = FAULTS
    _counts: dict[str, int] = field(default_factory=dict, repr=False)
    log: list[tuple[str, int, str]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not 0.0 <= self.rate <= 1.0:
            raise ValueError(f"fault rate must be in [0, 1], got {self.rate}")
        if not self.faults:
            raise ValueError("at least one fault profile is required")

    def next_fault(self, tool_name: str) -> ToolFault | None:
        """Decide the fate of the next call to ``tool_name``."""
        index = self._counts.get(tool_name, 0)
        self._counts[tool_name] = index + 1
        rng = random.Random(f"{self.seed}:{tool_name}:{index}")
        if rng.random() >= self.rate:
            return None
        fault = self.faults[rng.randrange(len(self.faults))]
        self.log.append((tool_name, index, fault.name))
        return fault

    def apply(self, tool_name: str, result: Any) -> Any:
        """Apply the next fault decision to a completed call's result."""
        fault = self.next_fault(tool_name)
        if fault is None:
            return result
        if fault.raises:
            raise InjectedFault(fault.name, fault.message)
        return fault.degrade(result) if fault.degrade else result


def wrap_callable(fn: Callable[..., Any], tool_name: str, injector: FaultInjector):
    """Wrap a sync or async callable so its results pass through the injector.

    A raising fault fires *before* the real call, so a simulated outage costs
    nothing; a degrading fault fires after, because it needs a real result to
    degrade.
    """
    import functools
    import inspect

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            fault = injector.next_fault(tool_name)
            if fault is not None and fault.raises:
                raise InjectedFault(fault.name, fault.message)
            result = await fn(*args, **kwargs)
            if fault is not None and fault.degrade is not None:
                return fault.degrade(result)
            return result

        return async_wrapper

    @functools.wraps(fn)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        fault = injector.next_fault(tool_name)
        if fault is not None and fault.raises:
            raise InjectedFault(fault.name, fault.message)
        result = fn(*args, **kwargs)
        if fault is not None and fault.degrade is not None:
            return fault.degrade(result)
        return result

    return sync_wrapper


# ---------------------------------------------------------------------------
# Structural: the same information, shaped differently
# ---------------------------------------------------------------------------

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?Z?$")

_TIME_KEYS = ("starttime", "endtime", "start_time", "end_time", "origin_time", "time")
_RENAMES = {"starttime": "start_time", "endtime": "end_time"}


def _to_epoch(value: str) -> float | str:
    try:
        text = value.replace("Z", "+00:00") if value.endswith("Z") else value
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return value


def _to_slashed(value: str) -> str:
    try:
        text = value.replace("Z", "+00:00") if value.endswith("Z") else value
        return datetime.fromisoformat(text).strftime("%Y/%m/%d %H:%M:%S")
    except ValueError:
        return value


def _t_epoch(obj: Any) -> Any:
    """ISO-8601 timestamps become epoch seconds."""
    if isinstance(obj, dict):
        return {
            k: (_to_epoch(v) if k in _TIME_KEYS and isinstance(v, str) else _t_epoch(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_t_epoch(v) for v in obj]
    if isinstance(obj, str) and _ISO.match(obj):
        return _to_epoch(obj)
    return obj


def _t_slashed(obj: Any) -> Any:
    """ISO-8601 timestamps become ``YYYY/MM/DD HH:MM:SS``."""
    if isinstance(obj, dict):
        return {
            k: (_to_slashed(v) if k in _TIME_KEYS and isinstance(v, str) else _t_slashed(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_t_slashed(v) for v in obj]
    if isinstance(obj, str) and _ISO.match(obj):
        return _to_slashed(obj)
    return obj


def _t_location_dashes(obj: Any) -> Any:
    """An empty location code spelled ``--`` instead of ``""``.

    The same location, and a genuine long-standing FDSN nuisance: ``""``,
    ``"--"`` and two spaces all mean "no location code", and clients disagree
    about which to send.
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ("location", "loc", "location_code") and v == "":
                out[k] = "--"
            else:
                out[k] = _t_location_dashes(v)
        return out
    if isinstance(obj, list):
        return [_t_location_dashes(v) for v in obj]
    if isinstance(obj, str):
        return re.sub(r"\b([A-Z0-9]{1,2})\.([A-Z0-9]{3,5})\.\.([A-Z]{3})\b", r"\1.\2.--.\3", obj)
    return obj


def _t_seed_id_dict(obj: Any) -> Any:
    """A dotted SEED id becomes its four named components."""
    if isinstance(obj, dict):
        return {k: _t_seed_id_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_t_seed_id_dict(v) for v in obj]
    if isinstance(obj, str):
        m = re.fullmatch(r"([A-Z0-9]{1,2})\.([A-Z0-9]{3,5})\.([A-Z0-9]{0,2}|--)\.([A-Z]{3})", obj)
        if m:
            loc = "" if m.group(3) == "--" else m.group(3)
            return {
                "network": m.group(1),
                "station": m.group(2),
                "location": loc,
                "channel": m.group(4),
            }
    return obj


def _t_key_naming(obj: Any) -> Any:
    """``starttime`` becomes ``start_time``, and so on."""
    if isinstance(obj, dict):
        return {_RENAMES.get(k, k): _t_key_naming(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_t_key_naming(v) for v in obj]
    return obj


def _t_key_order(obj: Any) -> Any:
    """Keys in reverse order. Same mapping; only a positional reader notices."""
    if isinstance(obj, dict):
        return {k: _t_key_order(obj[k]) for k in reversed(list(obj))}
    if isinstance(obj, list):
        return [_t_key_order(v) for v in obj]
    return obj


def _t_numeric_type(obj: Any) -> Any:
    """Integral sample rates and counts become floats: ``40`` -> ``40.0``."""
    if isinstance(obj, dict):
        return {k: _t_numeric_type(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_t_numeric_type(v) for v in obj]
    if isinstance(obj, int) and not isinstance(obj, bool):
        return float(obj)
    return obj


STRUCTURAL_TRANSFORMS: dict[str, Callable[[Any], Any]] = {
    "time_epoch": _t_epoch,
    "time_slashed": _t_slashed,
    "location_dashes": _t_location_dashes,
    "seed_id_dict": _t_seed_id_dict,
    "key_naming": _t_key_naming,
    "key_order": _t_key_order,
    "numeric_type": _t_numeric_type,
}


def perturb_structurally(
    value: Any, *, transforms: Iterable[str] | None = None, seed: int = 0, n: int = 2
) -> Any:
    """Apply ``n`` meaning-preserving reshapes, chosen reproducibly from the seed.

    Named transforms may be given explicitly instead; unknown names raise rather
    than being ignored, so a typo in a run configuration is not silently a
    weaker perturbation.
    """
    if transforms is None:
        rng = random.Random(f"structural:{seed}")
        names = rng.sample(sorted(STRUCTURAL_TRANSFORMS), k=min(n, len(STRUCTURAL_TRANSFORMS)))
    else:
        names = list(transforms)
        unknown = [t for t in names if t not in STRUCTURAL_TRANSFORMS]
        if unknown:
            raise ValueError(f"unknown structural transform(s): {unknown}")
    out = value
    for name in names:
        out = STRUCTURAL_TRANSFORMS[name](out)
    return out


# ---------------------------------------------------------------------------
# Prompt: the same request, asked differently
# ---------------------------------------------------------------------------

# Rule-based and deterministic on purpose. Generating paraphrases with a model
# would put a second model inside the measurement, and a robustness number would
# then depend on the paraphraser's mood as much as on the agent.
_PREFIXES = (
    "",
    "Please ",
    "I need you to ",
    "Your task: ",
    "Could you ",
)
_SUFFIXES = (
    "",
    " Show your work.",
    " Report what you did.",
    " Be precise.",
)
_SUBSTITUTIONS = (
    (r"\bcompute\b", "calculate"),
    (r"\bfetch\b", "retrieve"),
    (r"\bplot\b", "chart"),
    (r"\bfind\b", "locate"),
    (r"\bdetermine\b", "work out"),
    (r"\buse\b", "apply"),
    (r"\bwrite\b", "produce"),
)


def paraphrases(
    prompt: str,
    *,
    j: int = 5,
    seed: int = 0,
    authored: Mapping[str, list[str]] | None = None,
    item_id: str | None = None,
) -> list[str]:
    """Return ``j`` semantically equivalent rewordings, the original first.

    Authored paraphrases win when supplied: a domain expert's rewording of a
    seismology request is better than any rule, and the rules exist so the phase
    can run before anyone has written them.

    **These are never records.** RCA validator rule R08 bans
    ``holdout.construction: paraphrase_only`` on the test split, because a
    paraphrase of a catalog field is a leaked item. A robustness paraphrase is a
    measurement *over* an existing item, generated here at run time and written
    only to the run log, so R08 does not reach it. Do not write these to
    ``seeds/``.
    """
    if authored and item_id and authored.get(item_id):
        variants = [prompt, *authored[item_id]]
        return variants[:j]

    out = [prompt]
    rng = random.Random(f"paraphrase:{seed}:{prompt}")
    seen = {prompt}
    attempts = 0
    while len(out) < j and attempts < j * 20:
        attempts += 1
        text = prompt
        for pattern, replacement in _SUBSTITUTIONS:
            if rng.random() < 0.5:
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        prefix = rng.choice(_PREFIXES)
        if prefix and text:
            text = prefix + text[0].lower() + text[1:]
        text = text + rng.choice(_SUFFIXES)
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out


def wrap_registry_tools(names: list[str], injector: FaultInjector) -> list[Any]:
    """Resolve tools by name and wrap each so its calls pass through ``injector``.

    The perturbation is applied at the registry, not inside a suite, so it
    reaches every suite and every model identically. That preserves the rule in
    ``docs/agentic_eval.md``: hold the tool surface constant and vary only the
    model. A perturbed surface is still constant across models.
    """
    from repere.agents.registry import resolve_tools  # lazy: needs inspect_ai

    wrapped = []
    for name, tool in zip(names, resolve_tools(names), strict=True):
        if callable(tool):
            wrapped.append(wrap_callable(tool, name, injector))
        else:  # pragma: no cover - Inspect tool objects that are not callables
            wrapped.append(tool)
    return wrapped


def phase_metadata(phase: str, *, seed: int, rate: float | None = None) -> dict[str, Any]:
    """The provenance a perturbed row must carry to be interpretable."""
    if phase not in {"baseline", "fault", "structural", "prompt"}:
        raise ValueError(f"unknown phase {phase!r}")
    meta: dict[str, Any] = {"phase": phase, "perturbation_seed": seed}
    if phase == "fault":
        meta["fault_rate"] = DEFAULT_FAULT_RATE if rate is None else rate
    return meta


def summarise_injections(injector: FaultInjector) -> dict[str, int]:
    """How many of each fault actually fired, for the run log."""
    counts: dict[str, int] = {}
    for _tool, _index, fault_name in injector.log:
        counts[fault_name] = counts.get(fault_name, 0) + 1
    return counts


def _json_roundtrip(value: Any) -> Any:  # pragma: no cover - helper for callers
    return json.loads(json.dumps(value))
