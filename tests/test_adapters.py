from __future__ import annotations

import io
import json
from contextlib import contextmanager

import pytest

from repere import ModelCard
from repere.adapters import (
    AnthropicAdapter,
    EchoAdapter,
    OpenAICompatAdapter,
    adapter_from_env,
)


def _card(
    model_id: str, backend: str, in_rate: float = 0.001, out_rate: float = 0.002
) -> ModelCard:
    return ModelCard(
        id=model_id,
        family="test",
        size_b=7,
        context_window=8192,
        backend=backend,
        cost_per_1k_in=in_rate,
        cost_per_1k_out=out_rate,
    )


class _FakeHTTPResponse:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def _make_transport(captured: list, body: dict):
    def _transport(request, timeout=None):
        captured.append(
            {
                "url": request.full_url,
                "headers": dict(request.headers),
                "body": json.loads(request.data.decode()),
                "method": request.get_method(),
            }
        )
        return _FakeHTTPResponse(body)

    return _transport


# --- EchoAdapter ----------------------------------------------------------------


def test_echo_adapter_uses_canned_text_and_pricing():
    card = _card("echo-7b", "openai-compat", 0.001, 0.002)
    a = EchoAdapter(_card=card, response_text="hello there")
    g = a.generate("test prompt")
    assert g.text == "hello there"
    assert g.model_id == "echo-7b"
    # 1 token ≈ 4 chars; "test prompt" is 11 chars → 2 tokens, "hello there" is 11 → 2 tokens
    assert g.prompt_tokens == 2
    assert g.output_tokens == 2
    assert g.cost_usd == pytest.approx(2 / 1000 * 0.001 + 2 / 1000 * 0.002)


def test_echo_adapter_estimate_cost_uses_max_output_tokens():
    card = _card("echo-7b", "openai-compat", 0.001, 0.002)
    a = EchoAdapter(_card=card)
    est = a.estimate_cost("hello", max_output_tokens=500)
    assert est == pytest.approx(_approx_tokens("hello") / 1000 * 0.001 + 500 / 1000 * 0.002)


def _approx_tokens(s: str) -> int:
    return max(1, len(s) // 4)


def test_echo_adapter_response_fn_takes_prompt():
    card = _card("echo-7b", "openai-compat")
    a = EchoAdapter(_card=card, response_fn=lambda p: f"echo:{p}")
    g = a.generate("xyz")
    assert g.text == "echo:xyz"


# --- AnthropicAdapter -----------------------------------------------------------


def test_anthropic_adapter_posts_messages_and_parses_response():
    card = _card("claude-haiku-4-5", "anthropic", 1.0, 5.0)
    captured: list = []
    transport = _make_transport(
        captured,
        body={
            "id": "msg_01",
            "content": [{"type": "text", "text": "hello from claude"}],
            "usage": {"input_tokens": 12, "output_tokens": 7},
        },
    )
    a = AnthropicAdapter(_card=card, api_key="sk-test", transport=transport)
    g = a.generate("hi", max_output_tokens=50, temperature=0.0, system="you are terse")
    # request shape
    assert len(captured) == 1
    req = captured[0]
    assert req["url"].endswith("/v1/messages")
    assert req["headers"]["X-api-key"] == "sk-test"
    assert req["headers"]["Anthropic-version"]
    assert req["body"]["model"] == "claude-haiku-4-5"
    assert req["body"]["max_tokens"] == 50
    assert req["body"]["messages"] == [{"role": "user", "content": "hi"}]
    assert req["body"]["system"] == "you are terse"
    # response parsing
    assert g.text == "hello from claude"
    assert g.prompt_tokens == 12
    assert g.output_tokens == 7
    assert g.cost_usd == pytest.approx(12 / 1000 * 1.0 + 7 / 1000 * 5.0)


def test_anthropic_adapter_falls_back_when_usage_missing():
    card = _card("claude-haiku", "anthropic", 1.0, 5.0)
    captured: list = []
    transport = _make_transport(captured, body={"content": [{"type": "text", "text": "ok"}]})
    a = AnthropicAdapter(_card=card, api_key="sk", transport=transport)
    g = a.generate("hello")
    assert g.text == "ok"
    assert g.prompt_tokens >= 1
    assert g.output_tokens >= 1


# --- OpenAICompatAdapter --------------------------------------------------------


def test_openai_compat_adapter_posts_chat_completions():
    card = _card("mistral:7b", "ollama", 0.0, 0.0)
    captured: list = []
    transport = _make_transport(
        captured,
        body={
            "choices": [{"message": {"role": "assistant", "content": "pong"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        },
    )
    a = OpenAICompatAdapter(
        _card=card,
        base_url="http://127.0.0.1:11434",
        transport=transport,
    )
    g = a.generate("ping", system="be brief")
    assert captured[0]["url"].endswith("/v1/chat/completions")
    assert captured[0]["body"]["model"] == "mistral:7b"
    assert captured[0]["body"]["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "ping"},
    ]
    assert "Authorization" not in captured[0]["headers"]  # no key for local endpoint
    assert g.text == "pong"
    assert g.prompt_tokens == 3
    assert g.output_tokens == 1


def test_openai_compat_adapter_handles_block_content():
    card = _card("gpt-4o-mini", "openai", 0.15, 0.60)
    captured: list = []
    transport = _make_transport(
        captured,
        body={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "alpha "},
                            {"type": "text", "text": "beta"},
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        },
    )
    a = OpenAICompatAdapter(_card=card, api_key="sk-1234", transport=transport)
    g = a.generate("x")
    assert g.text == "alpha beta"
    assert captured[0]["headers"]["Authorization"] == "Bearer sk-1234"


def test_openai_compat_extra_headers_and_body_pass_through():
    card = _card("openrouter/foo", "openrouter", 0.001, 0.002)
    captured: list = []
    transport = _make_transport(
        captured,
        body={"choices": [{"message": {"content": "ok"}}], "usage": {}},
    )
    a = OpenAICompatAdapter(
        _card=card,
        api_key="key",
        base_url="https://openrouter.ai/api",
        extra_headers={"HTTP-Referer": "https://example.com"},
        extra_body={"top_p": 0.9},
        transport=transport,
    )
    a.generate("hello")
    assert captured[0]["headers"]["Http-referer"] == "https://example.com"
    assert captured[0]["body"]["top_p"] == 0.9


# --- adapter_from_env -----------------------------------------------------------


def test_adapter_from_env_picks_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anth")
    card = _card("claude", "anthropic")
    a = adapter_from_env(card)
    assert isinstance(a, AnthropicAdapter)
    assert a.api_key == "sk-anth"


def test_adapter_from_env_picks_openai_compat_for_ollama():
    card = _card("mistral", "ollama")
    a = adapter_from_env(card)
    assert isinstance(a, OpenAICompatAdapter)
    assert a.base_url.startswith("http://127.0.0.1:11434")


def test_adapter_from_env_unknown_backend():
    card = _card("foo", "unknown")
    with pytest.raises(ValueError):
        adapter_from_env(card)
