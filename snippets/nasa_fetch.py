"""Snippet for Member 2 - robust NASA POWER calls inside get_nasa_data().

Member 2 owns get_nasa_data() and the CSV cache. This only makes the HTTP call
resilient: connect/read timeouts, 3 retries with exponential backoff on
network errors and on 429/5xx, Retry-After respected, and a host allow-list
so the function can never be pointed at another server.

Usage inside get_nasa_data():

    from snippets.nasa_fetch import fetch_power
    try:
        payload = fetch_power(POWER_URL, params)
    except NasaUnavailable:
        df = read_cached_csv(...)   # Member 2's CSV cache takes over
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ALLOWED_HOSTS = {"power.larc.nasa.gov"}
TIMEOUT = (5, 30)  # (connect, read) in seconds


class NasaUnavailable(Exception):
    """NASA POWER could not be reached: use the local CSV cache."""


def build_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1.5,  # waits 0s, 3s, 6s
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "EarthTrendAI/1.0 (hackathon project)"})
    return session


_session = build_session()


def fetch_power(url: str, params: dict[str, Any]) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("only https://power.larc.nasa.gov is allowed")
    try:
        response = _session.get(url, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise NasaUnavailable(str(type(exc).__name__)) from exc
