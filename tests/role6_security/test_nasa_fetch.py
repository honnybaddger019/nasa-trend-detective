"""Deliverable 5 - the timeout + retry snippet given to Member 2."""

import pytest
import requests

from snippets import nasa_fetch


def test_session_retries_and_timeouts():
    adapter = nasa_fetch.build_session().get_adapter("https://power.larc.nasa.gov")
    retry = adapter.max_retries
    assert retry.total == 3
    assert set(retry.status_forcelist) == {429, 500, 502, 503, 504}
    assert retry.respect_retry_after_header
    assert nasa_fetch.TIMEOUT == (5, 30)


@pytest.mark.parametrize("url", ["http://power.larc.nasa.gov/api", "https://evil.example.com/api",
                                 "https://power.larc.nasa.gov.evil.com/api"])
def test_only_nasa_power_over_https_is_allowed(url):
    with pytest.raises(ValueError):
        nasa_fetch.fetch_power(url, {})


def test_network_failure_raises_nasa_unavailable(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(nasa_fetch._session, "get", fail)
    with pytest.raises(nasa_fetch.NasaUnavailable):
        nasa_fetch.fetch_power("https://power.larc.nasa.gov/api/temporal/monthly/point", {})
