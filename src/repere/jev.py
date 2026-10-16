"""Thin client for TypeSafe's System One API (Jev), for scoring free text.

Why this exists, and what it is *not*:

Repère's stance is a verifiable core — score against a reference with no model
in the loop wherever the task allows (``docs/lit_rag_scorers.md``). The two
places that stance runs out are (a) prose that cites sources, where the check
is "does this passage support this claim", and (b) prose that *reports* what an
agent did, where the check is "does the claim match the outcome we already
measured deterministically".

A free-text LLM judge can answer both, and the STA/LTA report scorer has one
(``scorers._call_judge``): render a prompt, generate, regex the score out of
the reply. It is expensive, unreproducible run to run, and its output is prose
we parse with a regex.

Jev is a different shape. It returns a typed answer plus a calibrated
probability distribution over the options *we* defined, and nothing else. No
prose to parse, the answer is constrained to our option set, and each question
is evaluated independently against the same state. That makes it composable in
code the way the deterministic scorers already are: the policy (weights,
thresholds, which dimensions matter) stays in this repository and is changed by
editing a number, not a prompt.

Price and limits, from https://docs.typesafe.ai/models.md, read 2026-09-22:
``jev-1.13.0`` costs $42 per billion *input* tokens; output tokens are free;
64k tokens per request total, 32k for the state plus the longest single
question; 250,000 tokens/s and 1,200 requests/minute.

The SDK is an optional dependency, imported lazily, so this module imports on a
machine that has never heard of TypeSafe. Nothing here calls the network unless
a caller constructs a client and asks a question.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# https://docs.typesafe.ai/models.md, read 2026-09-22: $42 per billion input
# tokens for jev-1.13.0. Output tokens are not billed. Pin the versioned id
# rather than the `jev-latest` alias: an alias moves when a release ships, and a
# leaderboard number has to name the model that produced it.
JEV_USD_PER_INPUT_TOKEN = 42.0 / 1e9
JEV_USD_PER_OUTPUT_TOKEN = 0.0
DEFAULT_MODEL = "jev-1.13.0"

# The state plus the longest question must fit in 32k tokens. We do not tokenize
# here; the runner truncates evidence before it gets this far. This constant is
# the documented ceiling, kept next to the price so both are in one place.
MAX_STATE_TOKENS = 32_000
MAX_REQUEST_TOKENS = 64_000

ENV_API_KEY = "TYPESAFE_API_KEY"
ENV_ENABLED = "REPERE_JEV_ENABLED"


class JevUnavailable(RuntimeError):
    """Raised when a Jev-backed scorer is asked to run without a way to run."""


@dataclass(frozen=True)
class JevUsage:
    """Token usage and the dollar cost it implies, per request."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        return (
            self.input_tokens * JEV_USD_PER_INPUT_TOKEN
            + self.output_tokens * JEV_USD_PER_OUTPUT_TOKEN
        )

    def __add__(self, other: JevUsage) -> JevUsage:
        return JevUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


@dataclass(frozen=True)
class JevResult:
    """One System One response: the typed answers, the model, the bill."""

    answers: dict[str, dict[str, Any]]
    model: str
    usage: JevUsage = field(default_factory=JevUsage)

    # -- typed readers -----------------------------------------------------
    #
    # Every reader raises KeyError on a missing question id rather than
    # returning a default. A scorer that silently reads 0.0 for a question the
    # service never answered reports a confident wrong number, which is the one
    # failure mode a benchmark cannot tolerate.

    def noul(self, question_id: str) -> float:
        """Probability that the answer to a yes/no question is yes."""
        return float(self.answers[question_id]["noul"])

    def choice(self, question_id: str) -> str:
        """The selected option of a Choice question."""
        return str(self.answers[question_id]["choice"])

    def score(self, question_id: str) -> float:
        """Position along a Score question's levels (0 .. n_levels - 1)."""
        return float(self.answers[question_id]["score"])

    def confidence(self, question_id: str) -> float:
        """How peaked the distribution is. Noul questions have no confidence.

        Returns 1.0 for a Noul so callers can apply one confidence gate across
        question types; read ``noul`` itself for a Noul's uncertainty, where
        0.5 means the model splits yes and no evenly.
        """
        answer = self.answers[question_id]
        if "confidence" not in answer:
            return 1.0
        return float(answer["confidence"])

    def probabilities(self, question_id: str) -> dict[str, float]:
        """The full distribution over options or levels, keys as strings."""
        raw = self.answers[question_id].get("probabilities", {})
        return {str(k): float(v) for k, v in raw.items()}


@runtime_checkable
class SystemOneTransport(Protocol):
    """The one call a Jev-backed scorer makes.

    Kept as a protocol so tests inject a recorded or scripted transport and the
    scorers are exercised in CI without a network, a key, or a bill — the same
    discipline ``tests/test_judge_fallback.py`` applies to the LLM judge.
    """

    def system_one(
        self,
        *,
        state: Any,
        questions: dict[str, dict[str, Any]],
        model: str,
    ) -> Any: ...


class SdkTransport:
    """Default transport: the ``typesafe-sdk`` synchronous client.

    Imported lazily and only on construction, so ``import repere.jev`` costs
    nothing on a machine without the SDK installed.
    """

    def __init__(self, *, api_key: str | None = None, timeout: float = 120.0):
        try:
            from typesafe_sdk import TypeSafeClient
        except ImportError as exc:  # pragma: no cover - exercised without the SDK
            raise JevUnavailable(
                "Jev scoring needs the TypeSafe SDK; install it with "
                "`pip install typesafe-sdk` (or `pixi add --pypi typesafe-sdk`)."
            ) from exc
        key = api_key or os.environ.get(ENV_API_KEY)
        if not key:
            raise JevUnavailable(
                f"Jev scoring needs {ENV_API_KEY} in the environment; create a "
                "key at https://console.typesafe.ai/ and put it in .env."
            )
        self._client = TypeSafeClient(api_key=key, timeout=timeout)

    def system_one(
        self,
        *,
        state: Any,
        questions: dict[str, dict[str, Any]],
        model: str,
    ) -> Any:
        return self._client.system_one(state=state, questions=questions, model=model)


def _as_mapping(obj: Any) -> dict[str, Any]:
    """Normalise an SDK response object or a raw JSON dict to one dict shape.

    The HTTP API returns ``{"model", "answers", "usage"}`` as JSON; the SDK
    returns typed objects over the same fields. Scorers should not care which
    one they were handed.
    """
    if isinstance(obj, dict):
        return obj
    for attr in ("model_dump", "dict", "to_dict"):
        dump = getattr(obj, attr, None)
        if callable(dump):
            dumped = dump()
            if isinstance(dumped, dict):
                return dumped
    return {key: getattr(obj, key) for key in ("model", "answers", "usage") if hasattr(obj, key)}


class JevClient:
    """Ask a batch of typed questions about one state, and price the call.

    One request, many questions: Jev ingests the state once and evaluates every
    question against it in parallel, so a second question costs its own tokens
    and almost no extra latency. Scorers here therefore ask every dimension of
    one item in a single call.
    """

    def __init__(
        self,
        transport: SystemOneTransport | None = None,
        *,
        model: str = DEFAULT_MODEL,
    ):
        self._transport = transport
        self.model = model
        self.total_usage = JevUsage()
        self.n_requests = 0

    @classmethod
    def from_env(cls, *, model: str = DEFAULT_MODEL) -> JevClient:
        """Build a live client, refusing unless scoring was explicitly enabled.

        Two gates, deliberately: ``REPERE_JEV_ENABLED=1`` says a human meant to
        spend money on this run, and ``TYPESAFE_API_KEY`` says the credential
        exists. A scorer that reaches the network because a key happened to be
        in the shell is how an eval run acquires a bill nobody planned.
        """
        if os.environ.get(ENV_ENABLED, "").lower() not in {"1", "true", "yes"}:
            raise JevUnavailable(
                f"Jev scoring is opt-in: set {ENV_ENABLED}=1 to allow network "
                "calls and a per-item charge."
            )
        return cls(SdkTransport(), model=model)

    def ask(
        self,
        state: Any,
        questions: dict[str, dict[str, Any]],
        *,
        model: str | None = None,
    ) -> JevResult:
        """Send one state and a map of typed questions; return typed answers."""
        if self._transport is None:
            raise JevUnavailable(
                "this JevClient has no transport; construct it with "
                "JevClient.from_env() or inject one for testing."
            )
        if not questions:
            raise ValueError("ask() needs at least one question")

        raw = _as_mapping(
            self._transport.system_one(
                state=state,
                questions=questions,
                model=model or self.model,
            )
        )
        answers = {
            str(qid): _as_mapping(answer) for qid, answer in (raw.get("answers") or {}).items()
        }
        missing = sorted(set(questions) - set(answers))
        if missing:
            raise JevUnavailable(f"Jev returned no answer for question ids: {missing}")
        usage_raw = _as_mapping(raw.get("usage") or {})
        usage = JevUsage(
            input_tokens=int(usage_raw.get("input_tokens", 0) or 0),
            output_tokens=int(usage_raw.get("output_tokens", 0) or 0),
        )
        self.total_usage = self.total_usage + usage
        self.n_requests += 1
        return JevResult(
            answers=answers,
            model=str(raw.get("model") or model or self.model),
            usage=usage,
        )


# ---------------------------------------------------------------------------
# Question constructors
#
# Plain dicts, matching the HTTP API body exactly
# (https://docs.typesafe.ai/api.md). Not the SDK's typed classes: the scorer
# specs in this repository have to stay JSON-serialisable so a suite row can
# carry its own scorer config, and a dict round-trips through JSONL untouched.
# ---------------------------------------------------------------------------


def noul(
    instructions: Any,
    *,
    true: Any | None = None,
    false: Any | None = None,
) -> dict[str, Any]:
    """A yes/no question. The answer is P(yes)."""
    q: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if true is not None or false is not None:
        q["criteria"] = {"true": true, "false": false}
    return q


def choice(instructions: Any, criteria: dict[str, Any]) -> dict[str, Any]:
    """Pick one of a named set of options. ``criteria`` maps option -> gloss."""
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def score(instructions: Any, levels: list[Any]) -> dict[str, Any]:
    """Rate against ordered levels, lowest first. Two to ten levels."""
    if not 2 <= len(levels) <= 10:
        raise ValueError("a Score question needs between 2 and 10 levels")
    return {"type": "score", "instructions": instructions, "criteria": list(levels)}
