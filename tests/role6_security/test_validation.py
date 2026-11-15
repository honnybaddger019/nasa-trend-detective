"""Deliverable 2 - strict input validation: invalid input gives 422, never 500."""

import json

import pytest

from security import AnalyzeRequest, CompareRequest, settings
from tests.role6_security.helpers import VALID, ip


def post(client, payload, path="/analyze", n=1):
    return client.post(path, json=payload, headers=ip(n))


def test_valid_request_is_accepted(client):
    response = post(client, VALID)
    assert response.status_code == 200
    assert response.json()["variable"] == "T2M"


@pytest.mark.parametrize(
    "field,value",
    [
        ("lat", 9999), ("lat", -90.0001), ("lat", 90.5), ("lon", 180.1), ("lon", -181),
        ("lat", "34.0"), ("lat", "abc"), ("lat", True), ("lat", None), ("lon", [1, 2]),
        ("start", 1950), ("start", 1980), ("end", 2200), ("start", 2000.5), ("start", "2000"),
        ("variable", "NDVI"), ("variable", "T2M; DROP TABLE x"), ("variable", ""),
        ("variable", "A" * 100), ("variable", 42),
    ],
)
def test_invalid_field_gives_422(client, field, value):
    payload = dict(VALID, **{field: value})
    response = post(client, payload)
    assert response.status_code == 422, (field, value, response.text)


def test_period_shorter_than_minimum_gives_422(client):
    response = post(client, dict(VALID, start=2020, end=2022))
    assert response.status_code == 422
    assert "at least" in response.text


def test_end_before_start_gives_422(client):
    assert post(client, dict(VALID, start=2024, end=2000)).status_code == 422


def test_unknown_field_is_rejected(client):
    assert post(client, dict(VALID, admin=True)).status_code == 422


@pytest.mark.parametrize("missing", ["lat", "lon", "start", "end", "variable"])
def test_missing_field_gives_422(client, missing):
    payload = {k: v for k, v in VALID.items() if k != missing}
    assert post(client, payload).status_code == 422


@pytest.mark.parametrize(
    "raw",
    [
        b"{not json",
        b"",
        b"[]",
        b'"just a string"',
        b'{"lat": NaN, "lon": 0, "start": 2000, "end": 2024, "variable": "T2M"}',
        b'{"lat": Infinity, "lon": 0, "start": 2000, "end": 2024, "variable": "T2M"}',
    ],
)
def test_malformed_body_gives_422(client, raw):
    response = client.post("/analyze", content=raw, headers={"Content-Type": "application/json", **ip(1)})
    assert response.status_code == 422, response.text


def test_variable_is_case_insensitive(client):
    response = post(client, dict(VALID, variable="prectotcorr"))
    assert response.status_code == 200
    assert response.json()["variable"] == "PRECTOTCORR"


def test_422_does_not_echo_submitted_values(client):
    secret_like = "<script>alert('x')</script>"
    response = post(client, dict(VALID, variable=secret_like))
    assert response.status_code == 422
    assert secret_like not in response.text
    body = response.json()
    assert body["detail"] == "Invalid request."
    assert body["errors"][0]["field"] == "variable"


def test_max_year_is_the_current_year_by_default():
    from datetime import datetime, timezone

    assert settings.max_year == datetime.now(timezone.utc).year


def test_models_can_be_used_without_fastapi():
    assert AnalyzeRequest(**VALID).variable == "T2M"
    with pytest.raises(ValueError):
        AnalyzeRequest(**dict(VALID, lat=9999))


def test_compare_request_validation():
    ok = {"region_a": {"lat": 34.03, "lon": -5.0}, "region_b": {"lat": 33.57, "lon": -7.59},
          "start": 2000, "end": 2024, "variable": "T2M"}
    assert CompareRequest(**ok).region_b.lat == 33.57
    with pytest.raises(ValueError):
        CompareRequest(**dict(ok, region_b={"lat": 999, "lon": 0}))
    with pytest.raises(ValueError):
        CompareRequest(**dict(ok, region_a={"lat": "1", "lon": 0}))


def test_no_invalid_input_ever_causes_a_500(client):
    """Fuzz the endpoints with many broken payloads: the server must never answer 500."""
    broken = [
        {}, {"lat": {}}, {"lat": 1e308}, {"lat": -1e308}, {"start": 10**30},
        dict(VALID, question=None), dict(VALID, question=""), dict(VALID, question=123),
        dict(VALID, question="x" * 10_000), dict(VALID, variable="\u0000"),
    ]
    n = 0
    for path in ("/analyze", "/explain", "/ask"):
        for payload in broken:
            n += 1
            response = client.post(path, content=json.dumps(payload),
                                   headers={"Content-Type": "application/json", **ip(100 + n % 100)})
            assert response.status_code in {200, 413, 422, 429}, (path, payload, response.status_code)
            assert response.status_code != 500
