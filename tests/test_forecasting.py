import pandas as pd
import pytest

from ai.forecasting import _prepare_series


def test_prepare_series_converts_to_prophet_columns():
    df = pd.DataFrame({
        "date": pd.date_range("2020-01-01", periods=24, freq="MS"),
        "value": range(24),
    })
    prepared = _prepare_series(df)
    assert list(prepared.columns) == ["ds", "y"]
    assert len(prepared) == 24


def test_prepare_series_rejects_too_few_rows():
    df = pd.DataFrame({
        "date": pd.date_range("2020-01-01", periods=12, freq="MS"),
        "value": range(12),
    })
    with pytest.raises(ValueError):
        _prepare_series(df)
