"""EarthTrend AI - provider-agnostic LLM client (Role 6).

The team will use a free LLM offer that is not chosen yet. This module hides
the provider behind one async method, so switching provider is a matter of
environment variables, not code:

    LLM_PROVIDER   none | mock | anthropic | gemini | groq | openrouter |
                   mistral | ollama | openai_compatible
    LLM_MODEL      model name for that provider (required except none/mock)
    LLM_API_KEY    secret key (never in the code or the repo)
    LLM_BASE_URL   only for openai_compatible (or to override a preset)

Security and resilience built in:
  * hard timeout, limited retries, bounded concurrency (protects the quota),
  * small in-memory cache: same stats + same question = no new API call,
  * every provider failure becomes LLMError, so the caller always falls back
    to the template text instead of returning an error 500,
  * the API key is never logged and never sent to the model.

Anthropic (Claude) is called with the official `anthropic` SDK. The other
providers expose an OpenAI-compatible Chat Completions endpoint and are called
over HTTPS with httpx.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("earthtrend.security")

# OpenAI-compatible endpoints of common providers that offer a free tier.
PRESETS: dict[str, str] = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "mistral": "https://api.mistral.ai/v1",
    "ollama": "http://127.0.0.1:11434/v1",
}
PROVIDERS = {"none", "mock", "anthropic", "openai_compatible", *PRESETS}

# Claude models that accept the server-side refusal fallback (`fallbacks: "default"`).
_ANTHROPIC_FALLBACK_MODELS = {
    "claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5",
}


class LLMError(Exception):
    """Any failure of the LLM call. The caller must use the fallback text."""


class LLMUnavailable(LLMError):
    """No provider configured (LLM_PROVIDER=none)."""


class LLMRefusal(LLMError):
    """The provider declined to answer (safety filter)."""


class LLMBadResponse(LLMError):
    """The provider answered with an unexpected or empty payload."""


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "none"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    timeout_s: float = 20.0
    max_retries: int = 1
    max_tokens: int = 1024
    temperature: float = 0.2
    anthropic_effort: str = "low"
    anthropic_server_fallback: bool = True
    max_concurrency: int = 4
    cache_ttl_s: int = 3600
    cache_max_entries: int = 256

    def __repr__(self) -> str:  # never print the key
        return f"LLMConfig(provider={self.provider!r}, model={self.model!r}, base_url={self.base_url!r})"


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


def load_llm_config() -> LLMConfig:
    provider = os.environ.get("LLM_PROVIDER", "none").strip().lower() or "none"
    if provider not in PROVIDERS:
        raise ValueError(f"LLM_PROVIDER must be one of {sorted(PROVIDERS)}, got {provider!r}")
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if provider == "anthropic" and not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    base_url = os.environ.get("LLM_BASE_URL", "").strip() or PRESETS.get(provider, "")
    model = os.environ.get("LLM_MODEL", "").strip()
    if provider == "anthropic" and not model:
        model = "claude-opus-5-5"
    if provider not in {"none", "mock"} and not model:
        raise ValueError("LLM_MODEL is required for this LLM_PROVIDER")
    if provider == "openai_compatible" and not base_url:
        raise ValueError("LLM_BASE_URL is required when LLM_PROVIDER=openai_compatible")
    if base_url and not base_url.startswith("https://") and provider != "ollama":
        raise ValueError("LLM_BASE_URL must use https://")
    effort = os.environ.get("LLM_ANTHROPIC_EFFORT", "low").strip().lower()
    if effort and effort not in {"low", "medium", "high", "xhigh", "max"}:
        raise ValueError("LLM_ANTHROPIC_EFFORT must be low, medium, high, xhigh, max or empty")
    return LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        timeout_s=_float_env("LLM_TIMEOUT_S", 20.0),
        max_retries=_int_env("LLM_MAX_RETRIES", 1),
        max_tokens=_int_env("LLM_MAX_TOKENS", 1024),
        temperature=_float_env("LLM_TEMPERATURE", 0.2),
        anthropic_effort=effort,
        anthropic_server_fallback=os.environ.get("LLM_ANTHROPIC_SERVER_FALLBACK", "true").strip().lower()
        in {"1", "true", "yes", "on"},
        max_concurrency=max(1, _int_env("LLM_MAX_CONCURRENCY", 4)),
        cache_ttl_s=max(0, _int_env("LLM_CACHE_TTL_S", 3600)),
        cache_max_entries=max(1, _int_env("LLM_CACHE_MAX_ENTRIES", 256)),
    )


class _TTLCache:
    def __init__(self, ttl_s: int, max_entries: int) -> None:
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._data: OrderedDict[str, tuple[float, str]] = OrderedDict()

    def get(self, key: str) -> str | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if expires < time.monotonic():
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: str) -> None:
        if self.ttl_s <= 0:
            return
        self._data[key] = (time.monotonic() + self.ttl_s, value)
        self._data.move_to_end(key)
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)


class LLMClient:
    """One async `complete(system, messages)` call, whatever the provider."""

    def __init__(self, config: LLMConfig, *, http_client: httpx.AsyncClient | None = None,
                 anthropic_client: Any | None = None) -> None:
        self.config = config
        self._http = http_client
        self._anthropic = anthropic_client
        self._cache = _TTLCache(config.cache_ttl_s, config.cache_max_entries)
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        self.mock_calls: list[dict[str, Any]] = []  # used by tests with LLM_PROVIDER=mock
        self.mock_reply = "The data shows a warming trend. The forecast error is reported with the result."

    @classmethod
    def from_env(cls) -> "LLMClient":
        return cls(load_llm_config())

    @property
    def enabled(self) -> bool:
        return self.config.provider != "none"

    def _cache_key(self, system: str, messages: list[dict[str, str]]) -> str:
        blob = json.dumps(
            [self.config.provider, self.config.model, self.config.max_tokens, system, messages],
            sort_keys=True, ensure_ascii=False,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    async def complete(self, system: str, messages: list[dict[str, str]]) -> str:
        if self.config.provider == "none":
            raise LLMUnavailable("no LLM provider configured")
        key = self._cache_key(system, messages)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        async with self._semaphore:
            if self.config.provider == "mock":
                self.mock_calls.append({"system": system, "messages": messages})
                text = self.mock_reply
            elif self.config.provider == "anthropic":
                text = await self._complete_anthropic(system, messages)
            else:
                text = await self._complete_openai_compatible(system, messages)
        if not text or not text.strip():
            raise LLMBadResponse("empty answer")
        self._cache.set(key, text)
        return text

    # -- Anthropic (official SDK) -------------------------------------------

    async def _complete_anthropic(self, system: str, messages: list[dict[str, str]]) -> str:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise LLMUnavailable("the anthropic package is not installed") from exc

        client = self._anthropic
        if client is None:
            client = anthropic.AsyncAnthropic(
                api_key=self.config.api_key or None,
                timeout=self.config.timeout_s,
                max_retries=self.config.max_retries,
            )
            self._anthropic = client

        # Current Claude models reject `temperature`: depth is set with effort.
        params: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "system": system,
            "messages": messages,
        }
        if self.config.anthropic_effort:
            params["output_config"] = {"effort": self.config.anthropic_effort}
        try:
            if self.config.anthropic_server_fallback and self.config.model in _ANTHROPIC_FALLBACK_MODELS:
                response = await client.beta.messages.create(
                    **params, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                )
            else:
                response = await client.messages.create(**params)
        except anthropic.AnthropicError as exc:
            raise LLMError(f"anthropic call failed: {type(exc).__name__}") from exc

        if response.stop_reason == "refusal":
            raise LLMRefusal("the model declined to answer")
        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        if not text.strip():
            raise LLMBadResponse(f"no text in the answer (stop_reason={response.stop_reason})")
        return text

    # -- OpenAI-compatible providers (Gemini, Groq, OpenRouter, ...) ----------

    async def _complete_openai_compatible(self, system: str, messages: list[dict[str, str]]) -> str:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        body = {
            "model": self.config.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }
        url = f"{self.config.base_url}/chat/completions"
        client = self._http or httpx.AsyncClient(timeout=self.config.timeout_s)
        try:
            response = None
            for attempt in range(self.config.max_retries + 1):
                try:
                    response = await client.post(url, headers=headers, json=body)
                except httpx.HTTPError as exc:
                    if attempt >= self.config.max_retries:
                        raise LLMError(f"provider unreachable: {type(exc).__name__}") from exc
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.config.max_retries:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                break
        finally:
            if self._http is None:
                await client.aclose()

        # The retry loop always sets response or raises.
        assert response is not None  # nosec B101
        if response.status_code != 200:
            # The provider error body may echo request data: log the status only.
            raise LLMError(f"provider returned HTTP {response.status_code}")
        try:
            choice = response.json()["choices"][0]
            text = choice["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMBadResponse("unexpected provider payload") from exc
        if choice.get("finish_reason") == "content_filter":
            raise LLMRefusal("the provider filtered the answer")
        return text
