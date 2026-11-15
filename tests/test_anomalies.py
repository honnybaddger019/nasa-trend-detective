import pandas as pd
import pytest

from ai.anomalies import detectAnomalies


def test_anomaly_function_returns_expected_keys():
    dates = pd.date_range("2018-01-01", periods=48, freq="MS")
    values = [
        15 + (i % 12) * 0.8 + i * 0.02
        for i in range(48)
    ]
    df = pd.DataFrame({"date": dates, "value": values})
    result = detectAnomalies(df, contamination=0.05)
    assert "anomalies" in result
    assert "all_observations" in result
    assert result["observations"] == 48


def test_anomaly_function_rejects_short_series():
    df = pd.DataFrame({
        "date": pd.date_range("2023-01-01", periods=12, freq="MS"),
        "value": range(12),
    })
    with pytest.raises(ValueError):
        detectAnomalies(df)
