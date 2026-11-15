"""Test configuration for the Role 6 security suite.

The environment is set BEFORE security.py is imported, because settings are
read once at import time (exactly like in production).
No real API key and no network access are needed.
"""

import os

os.environ.update(
    {
        "APP_ENV": "test",
        "LLM_PROVIDER": "mock",
        "LLM_API_KEY": "test-key-never-sent-to-the-model",
        "LLM_CACHE_TTL_S": "0",
        "RATE_LIMIT_ENABLED": "true",
        "RATE_LIMIT_LLM": "10/minute",
        "RATE_LIMIT_LLM_GLOBAL": "30/minute",
        "RATE_LIMIT_COMPUTE": "30/minute",
        "TRUSTED_PROXY_HOPS": "1",
        "ALLOWED_ORIGINS": "https://earthtrend.example.org",
        "MAX_BODY_BYTES": "16384",
        "DEBUG_CLIENT_IP": "true",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from examples import demo_server  # noqa: E402
from security import limiter  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_state():
    limiter.reset()
    demo_server.llm.mock_calls.clear()
    yield
    limiter.reset()


@pytest.fixture
def client():
    with TestClient(demo_server.app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def llm():
    return demo_server.llm
