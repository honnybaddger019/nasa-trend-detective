"""Deliverable 2 - rate limiting: the 11th LLM call in one minute gives 429."""

from security import limit_llm, settings
from tests.role6_security.helpers import VALID, ip


def test_eleventh_call_in_a_minute_gives_429(client):
    codes = [client.post("/explain", json=VALID, headers=ip(1)).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10
    assert codes[10] == 429


def test_429_has_retry_after_and_clean_body(client):
    for _ in range(10):
        client.post("/explain", json=VALID, headers=ip(2))
    response = client.post("/explain", json=VALID, headers=ip(2))
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert response.json() == {"detail": "Too many requests. Please retry in a minute."}
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_limit_is_per_client_ip(client):
    for _ in range(10):
        assert client.post("/explain", json=VALID, headers=ip(3)).status_code == 200
    assert client.post("/explain", json=VALID, headers=ip(3)).status_code == 429
    assert client.post("/explain", json=VALID, headers=ip(4)).status_code == 200


def test_each_llm_route_has_its_own_per_ip_counter(client):
    # Each route has its own per-IP counter, both count towards the global cap.
    for _ in range(10):
        assert client.post("/explain", json=VALID, headers=ip(5)).status_code == 200
    ask = dict(VALID, question="Was 2022 unusual?")
    assert client.post("/ask", json=ask, headers=ip(5)).status_code == 200


def test_global_cap_protects_the_llm_quota_against_ip_rotation(client):
    # 30/minute shared by every client, even if each request uses a new IP.
    codes = [client.post("/explain", json=VALID, headers=ip(10 + i)).status_code for i in range(31)]
    assert codes[:30] == [200] * 30
    assert codes[30] == 429


def test_forged_x_forwarded_for_cannot_bypass_the_limit(client):
    # The attacker controls the left part of X-Forwarded-For, the proxy appends the real IP.
    real = "198.51.100.7"
    for i in range(10):
        headers = {"X-Forwarded-For": f"10.0.0.{i}, {real}"}
        assert client.post("/explain", json=VALID, headers=headers).status_code == 200
    headers = {"X-Forwarded-For": f"10.9.9.9, {real}"}
    assert client.post("/explain", json=VALID, headers=headers).status_code == 429


def test_invalid_input_does_not_consume_the_llm_budget(client):
    for _ in range(20):
        assert client.post("/explain", json=dict(VALID, lat=9999), headers=ip(6)).status_code == 422
    assert client.post("/explain", json=VALID, headers=ip(6)).status_code == 200


def test_compute_route_has_its_own_limit(client):
    codes = [client.post("/analyze", json=VALID, headers=ip(7)).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30
    assert codes[30] == 429


def test_health_is_never_rate_limited(client):
    for _ in range(100):
        assert client.get("/health", headers=ip(8)).status_code == 200


def test_settings_used_by_the_suite():
    assert settings.rate_limit_llm == "10/minute"
    assert callable(limit_llm)
