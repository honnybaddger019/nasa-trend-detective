"""Deliverable 2/5 - security headers, CORS, body limit, generic errors, /health."""

import dataclasses

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from security import build_csp, build_security_headers, install_security, settings
from tests.role6_security.helpers import VALID, ip

REQUIRED = ["Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy", "X-Frame-Options"]


@pytest.mark.parametrize("path", ["/", "/health"])
def test_security_headers_on_every_response(client, path):
    response = client.get(path, headers=ip(1))
    for name in REQUIRED:
        assert name in response.headers, name
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert len(response.headers["X-Request-ID"]) == 16


def test_headers_are_also_on_error_responses(client):
    for response in (
        client.get("/does-not-exist", headers=ip(1)),
        client.post("/analyze", json={"lat": 9999}, headers=ip(1)),
    ):
        assert response.status_code in {404, 422}
        assert "Content-Security-Policy" in response.headers


def test_csp_allows_the_app_and_blocks_the_rest():
    csp = build_csp(settings)
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert "https://cdn.plot.ly" in csp                      # Plotly charts
    assert "connect-src 'self' https://power.larc.nasa.gov" in csp  # browser-only mode
    assert "'unsafe-eval'" not in csp
    script_src = next(d for d in csp.split("; ") if d.startswith("script-src"))
    assert "'unsafe-inline'" not in script_src  # inline scripts stay blocked (XSS)


def test_netlify_headers_file_matches_the_backend_headers():
    from pathlib import Path

    expected = build_security_headers(dataclasses.replace(settings, app_env="production"))
    lines = Path("static/_headers").read_text().splitlines()
    assert "/*" in lines
    found = dict(line.strip().split(": ", 1) for line in lines if line.startswith("  "))
    assert found == expected


def test_hsts_only_in_production():
    assert "Strict-Transport-Security" not in build_security_headers(settings)
    prod = dataclasses.replace(settings, app_env="production")
    assert build_security_headers(prod)["Strict-Transport-Security"].startswith("max-age=31536000")


def test_report_only_mode_switch():
    report_only = dataclasses.replace(settings, csp_report_only=True)
    headers = build_security_headers(report_only)
    assert "Content-Security-Policy-Report-Only" in headers
    assert "Content-Security-Policy" not in headers


def test_json_api_responses_are_not_cached(client):
    response = client.post("/analyze", json=VALID, headers=ip(1))
    assert response.headers["Cache-Control"] == "no-store"


def test_cors_allows_only_the_configured_origin(client):
    good = client.options("/explain", headers={
        "Origin": "https://earthtrend.example.org", "Access-Control-Request-Method": "POST"})
    assert good.headers.get("access-control-allow-origin") == "https://earthtrend.example.org"
    evil = client.options("/explain", headers={
        "Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in evil.headers
    simple = client.post("/analyze", json=VALID, headers={"Origin": "https://evil.example.com", **ip(1)})
    assert "access-control-allow-origin" not in simple.headers


def test_body_larger_than_limit_gives_413(client):
    huge = dict(VALID, question="a" * 20_000)
    response = client.post("/ask", json=huge, headers=ip(1))
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large."}
    assert "Content-Security-Policy" in response.headers


def test_chunked_body_larger_than_limit_is_rejected(client):
    def chunks():
        for _ in range(40):
            yield b"a" * 1024

    response = client.post("/ask", content=chunks(), headers={"Content-Type": "application/json", **ip(1)})
    assert response.status_code in {400, 413, 422}
    assert response.status_code != 500


def test_unexpected_error_gives_generic_500_without_details():
    app = FastAPI()
    install_security(app)

    @app.get("/boom")
    async def boom(request: Request):
        raise RuntimeError("database password is hunter2")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error."
    assert len(body["request_id"]) == 16
    assert "hunter2" not in response.text and "Traceback" not in response.text
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_health_endpoint(client):
    response = client.get("/health", headers={"X-Forwarded-For": "1.2.3.4, 198.51.100.9"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # DEBUG_CLIENT_IP=true in the test env: shows which IP the limiter uses.
    assert body["client_ip"] == "198.51.100.9"


def test_docs_are_hidden_in_production(monkeypatch):
    import security

    monkeypatch.setattr(security, "settings", dataclasses.replace(settings, app_env="production"))
    app = FastAPI()
    security.install_security(app)
    with TestClient(app) as test_client:
        assert test_client.get("/docs").status_code == 404
        assert test_client.get("/openapi.json").status_code == 404
