"""Provider adapters for FrugalMind.

The `Adapter` protocol lives in :mod:`frugalmind`. This module ships three
concrete implementations:

- :class:`EchoAdapter` — deterministic, no-network adapter for tests.
- :class:`AnthropicAdapter` — Anthropic Messages API.
- :class:`OpenAICompatAdapter` — OpenAI-compatible chat-completions endpoint
  (works with OpenAI, OpenRouter, Ollama, vLLM, LM Studio, etc.).

Both HTTP adapters use stdlib `urllib` so the package has no new runtime
dependencies. They are tested with mocked transport; live API calls are out of
scope for the deterministic test suite.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from . import Generation, ModelCard


def _approx_token_count(text: str) -> int:
    """Cheap token estimate: 1 token ≈ 4 characters of English text."""
    return max(1, len(text) // 4)


def _http_post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    *,
    timeout_s: float,
    transport: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """POST JSON to a URL and return parsed JSON; transport is injectable for tests."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    opener = transport or urllib.request.urlopen
    try:
        with opener(request, timeout=timeout_s) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Request to {url} failed: {exc.reason}") from exc
    if not body:
        return {}
    return json.loads(body)


@dataclass
class EchoAdapter:
    """Deterministic adapter that returns canned text and accounting.

    Used in tests and to mock backends without network access.
    """

    _card: ModelCard
    response_text: str = ""
    response_fn: Callable[[str], str] | None = None
    fixed_latency_s: float = 0.0
    cost_per_1k_in: float | None = None
    cost_per_1k_out: float | None = None

    @property
    def card(self) -> ModelCard:
        return self._card

    def _resolve_text(self, prompt: str) -> str:
        if self.response_fn is not None:
            return self.response_fn(prompt)
        return self.response_text

    def estimate_cost(self, prompt: str, *, max_output_tokens: int = 256, **_: Any) -> float:
        in_rate = (
            self.cost_per_1k_in if self.cost_per_1k_in is not None else self._card.cost_per_1k_in
        )
        out_rate = (
            self.cost_per_1k_out if self.cost_per_1k_out is not None else self._card.cost_per_1k_out
        )
        in_tokens = _approx_token_count(prompt)
        return (in_tokens / 1000.0) * in_rate + (max_output_tokens / 1000.0) * out_rate

    def generate(self, prompt: str, *, max_output_tokens: int = 256, **_: Any) -> Generation:
        text = self._resolve_text(prompt)
        in_tokens = _approx_token_count(prompt)
        out_tokens = _approx_token_count(text)
        in_rate = (
            self.cost_per_1k_in if self.cost_per_1k_in is not None else self._card.cost_per_1k_in
        )
        out_rate = (
            self.cost_per_1k_out if self.cost_per_1k_out is not None else self._card.cost_per_1k_out
        )
        cost = (in_tokens / 1000.0) * in_rate + (out_tokens / 1000.0) * out_rate
        return Generation(
            text=text,
            prompt_tokens=in_tokens,
            output_tokens=out_tokens,
            latency_s=self.fixed_latency_s,
            cost_usd=cost,
            model_id=self._card.id,
        )


@dataclass
class AnthropicAdapter:
    """Adapter for Anthropic's Messages API.

    Pricing comes from the model card; usage from the API response. Use
    :class:`EchoAdapter` for deterministic tests rather than mocking the network
    in unit tests of consumers.
    """

    _card: ModelCard
    api_key: str
    base_url: str = "https://api.anthropic.com"
    default_max_tokens: int = 1024
    anthropic_version: str = "2023-06-01"
    timeout_s: float = 120.0
    transport: Callable[..., Any] | None = None  # for tests

    @property
    def card(self) -> ModelCard:
        return self._card

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.anthropic_version,
            "content-type": "application/json",
        }

    def estimate_cost(
        self, prompt: str, *, max_output_tokens: int | None = None, **_: Any
    ) -> float:
        in_tokens = _approx_token_count(prompt)
        out_tokens = max_output_tokens if max_output_tokens is not None else self.default_max_tokens
        return (
            in_tokens / 1000.0 * self._card.cost_per_1k_in
            + out_tokens / 1000.0 * self._card.cost_per_1k_out
        )

    # Anthropic prompt-cache pricing multipliers, relative to base input price.
    # Writing to the cache costs a premium; reading from it is nearly free. A
    # long static prefix reused across N items therefore approaches ~1/N of its
    # uncached cost. See https://docs.anthropic.com/en/docs/prompt-caching
    CACHE_WRITE_MULT: float = 1.25
    CACHE_READ_MULT: float = 0.10

    def generate(
        self,
        prompt: str,
        *,
        max_output_tokens: int | None = None,
        temperature: float = 0.0,
        system: str | None = None,
        cache_prefix: str | None = None,
        **_: Any,
    ) -> Generation:
        """Generate a completion.

        ``cache_prefix`` is a static leading block — typically the injected
        domain skill, identical across every item in a suite — marked for
        provider-side caching. It is sent as the first content block of the same
        user message, so ``cache_prefix + prompt`` is byte-identical to the
        prompt we would otherwise have sent: caching changes the price, never
        the text the model sees.

        Note the provider enforces a minimum cacheable block length (larger for
        the smaller models), so a short skill may simply not cache. The usage
        fields below report what actually happened rather than what we intended.
        """
        url = f"{self.base_url.rstrip('/')}/v1/messages"
        if cache_prefix:
            content: Any = [
                {
                    "type": "text",
                    "text": cache_prefix,
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": prompt},
            ]
        else:
            content = prompt
        body: dict[str, Any] = {
            "model": self._card.id,
            "max_tokens": max_output_tokens or self.default_max_tokens,
            "messages": [{"role": "user", "content": content}],
            "temperature": temperature,
        }
        if system:
            body["system"] = system

        start = time.perf_counter()
        data = _http_post_json(
            url, body, self._headers(), timeout_s=self.timeout_s, transport=self.transport
        )
        latency_s = time.perf_counter() - start

        text = ""
        for block in data.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")

        usage = data.get("usage", {}) or {}
        in_tokens = int(usage.get("input_tokens", _approx_token_count(prompt)))
        out_tokens = int(usage.get("output_tokens", _approx_token_count(text)))
        cache_write = int(usage.get("cache_creation_input_tokens", 0) or 0)
        cache_read = int(usage.get("cache_read_input_tokens", 0) or 0)

        rate_in = self._card.cost_per_1k_in / 1000.0
        cost = (
            in_tokens * rate_in
            + cache_write * rate_in * self.CACHE_WRITE_MULT
            + cache_read * rate_in * self.CACHE_READ_MULT
            + out_tokens / 1000.0 * self._card.cost_per_1k_out
        )
        return Generation(
            text=text,
            # Report every input token the request actually consumed, cached or
            # not, so token-based accounting stays honest.
            prompt_tokens=in_tokens + cache_write + cache_read,
            output_tokens=out_tokens,
            latency_s=latency_s,
            cost_usd=cost,
            model_id=self._card.id,
        )


@dataclass
class OpenAICompatAdapter:
    """Adapter for OpenAI-compatible chat-completions endpoints.

    Compatible with OpenAI, OpenRouter, Ollama (`/v1/chat/completions`), vLLM,
    LM Studio, and other OpenAI-API-compatible servers.
    """

    _card: ModelCard
    api_key: str | None = None
    base_url: str = "https://api.openai.com"
    default_max_tokens: int = 1024
    timeout_s: float = 120.0
    extra_headers: dict[str, str] | None = None
    extra_body: dict[str, Any] | None = None
    transport: Callable[..., Any] | None = None  # for tests

    @property
    def card(self) -> ModelCard:
        return self._card

    def _headers(self) -> dict[str, str]:
        h = {"content-type": "application/json"}
        if self.api_key:
            h["authorization"] = f"Bearer {self.api_key}"
        if self.extra_headers:
            h.update(self.extra_headers)
        return h

    def estimate_cost(
        self, prompt: str, *, max_output_tokens: int | None = None, **_: Any
    ) -> float:
        in_tokens = _approx_token_count(prompt)
        out_tokens = max_output_tokens if max_output_tokens is not None else self.default_max_tokens
        return (
            in_tokens / 1000.0 * self._card.cost_per_1k_in
            + out_tokens / 1000.0 * self._card.cost_per_1k_out
        )

    def generate(
        self,
        prompt: str,
        *,
        max_output_tokens: int | None = None,
        temperature: float = 0.0,
        system: str | None = None,
        **_: Any,
    ) -> Generation:
        url = f"{self.base_url.rstrip('/')}/v1/chat/completions"
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {
            "model": self._card.id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_output_tokens or self.default_max_tokens,
        }
        if self.extra_body:
            body.update(self.extra_body)

        start = time.perf_counter()
        data = _http_post_json(
            url, body, self._headers(), timeout_s=self.timeout_s, transport=self.transport
        )
        latency_s = time.perf_counter() - start

        text = ""
        choices: Iterable[dict[str, Any]] = data.get("choices", []) or []
        for choice in choices:
            msg = choice.get("message") or {}
            content = msg.get("content")
            if isinstance(content, str):
                text += content
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        text += str(block["text"])

        usage = data.get("usage", {}) or {}
        in_tokens = int(usage.get("prompt_tokens", _approx_token_count(prompt)))
        out_tokens = int(usage.get("completion_tokens", _approx_token_count(text)))
        cost = (
            in_tokens / 1000.0 * self._card.cost_per_1k_in
            + out_tokens / 1000.0 * self._card.cost_per_1k_out
        )
        return Generation(
            text=text,
            prompt_tokens=in_tokens,
            output_tokens=out_tokens,
            latency_s=latency_s,
            cost_usd=cost,
            model_id=self._card.id,
        )


def adapter_from_env(card: ModelCard, **kwargs: Any):
    """Convenience factory: pick adapter class from `card.backend`.

    Reads API keys from the environment:
      - anthropic: ANTHROPIC_API_KEY
      - openai:    OPENAI_API_KEY
      - openrouter: OPENROUTER_API_KEY
      - openai-compat / ollama / vllm: OPENAI_API_KEY (optional)
    """
    backend = card.backend.lower()
    if backend == "anthropic":
        api_key = kwargs.pop("api_key", None) or os.environ.get("ANTHROPIC_API_KEY", "")
        return AnthropicAdapter(_card=card, api_key=api_key, **kwargs)
    if backend in ("openai", "openrouter", "openai-compat", "ollama", "vllm", "lm-studio"):
        defaults = {
            "openai": ("https://api.openai.com", "OPENAI_API_KEY"),
            "openrouter": ("https://openrouter.ai/api", "OPENROUTER_API_KEY"),
            "ollama": ("http://127.0.0.1:11434", None),
            "vllm": ("http://127.0.0.1:8000", None),
            "lm-studio": ("http://127.0.0.1:1234", None),
            "openai-compat": ("http://127.0.0.1:8080", None),
        }
        base, env_key = defaults[backend]
        kwargs.setdefault("base_url", base)
        api_key = kwargs.pop("api_key", None)
        if api_key is None and env_key is not None:
            api_key = os.environ.get(env_key)
        return OpenAICompatAdapter(_card=card, api_key=api_key, **kwargs)
    raise ValueError(f"Unknown backend {backend!r}; supported: anthropic, openai-compat family")


__all__ = [
    "AnthropicAdapter",
    "EchoAdapter",
    "OpenAICompatAdapter",
    "adapter_from_env",
]
