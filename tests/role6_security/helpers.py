"""Shared test data for the Role 6 security suite."""

VALID = {"lat": 34.03, "lon": -5.0, "start": 2000, "end": 2024, "variable": "T2M"}


def ip(n: int) -> dict[str, str]:
    """Headers that make a request come from a distinct client IP."""
    return {"X-Forwarded-For": f"203.0.113.{n}"}
