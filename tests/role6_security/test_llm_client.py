"""Provider-agnostic LLM client: request shape, errors -> fallback, cache, config."""

import asyncio
import json

import httpx
import pytest

from llm_client import (
    LLMBadResponse,
    LLMClient,
    LLMConfig,
    LLMError,
    LLMRefusal,
    LLMUnavailable,
    load_llm_config,
)

SYSTEM = "system prompt"
MESSAGES = [{"role": "user", "content": "<stats>{}</stats>"}]


def run(coro):
    return asyncio.run(coro)


def openai_client(handler, **overrides):
    config = LLMConfig(provider="groq", model="test-model", api_key="k-test",
                       base_url="https://api.example.test/v1", max_retries=1, **overrides)
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return LLMClient(config, http_client=http)


def test_openai_compatible_request_and_answer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "The data shows X."},
                                                      "finish_reason": "stop"}]})

    client = openai_client(handler)
    assert run(client.complete(SYSTEM, MESSAGES)) == "The data shows X."
    assert seen["url"] == "https://api.example.test/v1/chat/completions"
    assert seen["auth"] == "Bearer k-test"
    assert seen["body"]["messages"][0] == {"role": "system", "content": SYSTEM}
    assert seen["body"]["max_tokens"] == 1024


@pytest.mark.parametrize(
    "response,error",
    [
        (httpx.Response(401, json={"error": "bad key"}), LLMError),
        (httpx.Response(500, text="oops"), LLMError),
        (httpx.Response(200, text="not json"), LLMBadResponse),
        (httpx.Response(200, json={"choices": []}), LLMBadResponse),
        (httpx.Response(200, json={"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}), LLMBadResponse),
        (httpx.Response(200, json={"choices": [{"message": {"content": "x"}, "finish_reason": "content_filter"}]}), LLMRefusal),
    ],
)
def test_openai_compatible_errors_become_llm_errors(response, error, monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    client = openai_client(lambda request: response)
    with pytest.raises(error):
        run(client.complete(SYSTEM, MESSAGES))


async def _no_sleep(_seconds):
    return None


def test_openai_compatible_retries_once_on_429(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

    assert run(openai_client(handler).complete(SYSTEM, MESSAGES)) == "ok"
    assert calls["n"] == 2


def test_network_error_becomes_llm_error(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    def handler(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    with pytest.raises(LLMError):
        run(openai_client(handler).complete(SYSTEM, MESSAGES))


def test_cache_avoids_a_second_call():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "cached"}, "finish_reason": "stop"}]})

    client = openai_client(handler, cache_ttl_s=60)
    assert run(client.complete(SYSTEM, MESSAGES)) == "cached"
    assert run(client.complete(SYSTEM, MESSAGES)) == "cached"
    assert calls["n"] == 1


def test_provider_none_raises_unavailable():
    with pytest.raises(LLMUnavailable):
        run(LLMClient(LLMConfig(provider="none")).complete(SYSTEM, MESSAGES))


# --- Anthropic adapter (official SDK, mocked HTTP transport) ----------------

def anthropic_client(handler, model="claude-opus-5-5", fallback=True):
    import anthropic
    import httpx2

    sdk = anthropic.AsyncAnthropic(
        api_key="k-test", max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    config = LLMConfig(provider="anthropic", model=model, api_key="k-test",
                       anthropic_server_fallback=fallback)
    return LLMClient(config, anthropic_client=sdk)


def _message(text="The data shows Y.", stop_reason="end_turn", content=None):
    return {
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": content if content is not None else [{"type": "text", "text": text}],
        "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def test_anthropic_request_shape_has_no_temperature():
    import httpx2

    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta", "")
        return httpx2.Response(200, json=_message())

    assert run(anthropic_client(handler).complete(SYSTEM, MESSAGES)) == "The data shows Y."
    body = seen["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["system"] == SYSTEM
    assert body["messages"] == MESSAGES
    assert body["output_config"] == {"effort": "low"}
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in seen["beta"]
    assert "temperature" not in body  # rejected by current Claude models


def test_anthropic_without_server_fallback_uses_plain_endpoint():
    import httpx2

    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta", "")
        return httpx2.Response(200, json=_message())

    run(anthropic_client(handler, model="claude-haiku-5-5").complete(SYSTEM, MESSAGES))
    assert "fallbacks" not in seen["body"] and seen["beta"] == ""


def test_anthropic_refusal_becomes_llm_refusal():
    import httpx2

    handler = lambda request: httpx2.Response(200, json=_message(stop_reason="refusal", content=[]))  # noqa: E731
    with pytest.raises(LLMRefusal):
        run(anthropic_client(handler).complete(SYSTEM, MESSAGES))


@pytest.mark.parametrize("status", [400, 401, 429, 500, 529])
def test_anthropic_http_errors_become_llm_errors(status):
    import httpx2

    handler = lambda request: httpx2.Response(status, json={"type": "error", "error": {"type": "x", "message": "m"}})  # noqa: E731
    with pytest.raises(LLMError):
        run(anthropic_client(handler).complete(SYSTEM, MESSAGES))


def test_anthropic_empty_text_is_bad_response():
    import httpx2

    handler = lambda request: httpx2.Response(200, json=_message(stop_reason="max_tokens", content=[]))  # noqa: E731
    with pytest.raises(LLMBadResponse):
        run(anthropic_client(handler).complete(SYSTEM, MESSAGES))


# --- Configuration ----------------------------------------------------------

def test_config_presets(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_MODEL", "some-model")
    config = load_llm_config()
    assert config.base_url == "https://generativelanguage.googleapis.com/v1beta/openai"


@pytest.mark.parametrize(
    "env",
    [
        {"LLM_PROVIDER": "unknown"},
        {"LLM_PROVIDER": "groq", "LLM_MODEL": ""},
        {"LLM_PROVIDER": "openai_compatible", "LLM_MODEL": "m", "LLM_BASE_URL": ""},
        {"LLM_PROVIDER": "openai_compatible", "LLM_MODEL": "m", "LLM_BASE_URL": "http://insecure.example"},
        {"LLM_PROVIDER": "anthropic", "LLM_ANTHROPIC_EFFORT": "huge"},
    ],
)
def test_invalid_config_fails_fast(monkeypatch, env):
    for key in ("LLM_MODEL", "LLM_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        load_llm_config()


def test_config_repr_never_shows_the_key():
    config = LLMConfig(provider="groq", model="m", api_key="super-secret-value")
    assert "super-secret-value" not in repr(config)
