"""Forecasting and backtesting for monthly environmental time series.

Expected input:
    pandas.DataFrame with a date column and a numeric value column.
Prophet expects columns named ds (date) and y (observed value).
"""

from __future__ import annotations

from typing import Any
import pandas as pd
from prophet import Prophet
from sklearn.metrics import mean_absolute_error


def _prepare_series(
    data: pd.DataFrame,
    date_col: str = "date",
    value_col: str = "value",
) -> pd.DataFrame:
    """Validate and convert input data to Prophet's ds/y format."""
    if not isinstance(data, pd.DataFrame):
        raise TypeError("data must be a pandas DataFrame")

    missing = [col for col in (date_col, value_col) if col not in data.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = data[[date_col, value_col]].copy()
    df.columns = ["ds", "y"]
    df["ds"] = pd.to_datetime(df["ds"], errors="coerce")
    df["y"] = pd.to_numeric(df["y"], errors="coerce")
    df = df.dropna(subset=["ds", "y"]).sort_values("ds")
    df = df.drop_duplicates(subset=["ds"], keep="last").reset_index(drop=True)

    if len(df) < 24:
        raise ValueError(
            "At least 24 valid observations are required; monthly data "
            "covering at least two years is recommended."
        )
    return df


def forecast(
    data: pd.DataFrame,
    periods: int = 36,
    date_col: str = "date",
    value_col: str = "value",
    interval_width: float = 0.95,
) -> dict[str, Any]:
    """Fit Prophet and forecast the next `periods` monthly observations.

    Returns a JSON-serializable dictionary with historical data and forecast.
    """
    if periods < 1:
        raise ValueError("periods must be at least 1")
    if not 0 < interval_width < 1:
        raise ValueError("interval_width must be between 0 and 1")

    df = _prepare_series(data, date_col, value_col)
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        interval_width=interval_width,
    )
    model.fit(df)

    future = model.make_future_dataframe(periods=periods, freq="MS")
    prediction = model.predict(future)

    # Return only the future rows in the forecast section.
    future_prediction = prediction[prediction["ds"] > df["ds"].max()]
    columns = ["ds", "yhat", "yhat_lower", "yhat_upper"]
    future_prediction = future_prediction[columns].copy()
    future_prediction["ds"] = future_prediction["ds"].dt.strftime("%Y-%m-%d")

    return {
        "model": "Prophet",
        "periods": periods,
        "interval_width": interval_width,
        "last_observed_date": df["ds"].max().strftime("%Y-%m-%d"),
        "forecast": future_prediction.to_dict(orient="records"),
    }


def backtest(
    data: pd.DataFrame,
    test_months: int = 36,
    date_col: str = "date",
    value_col: str = "value",
) -> dict[str, Any]:
    """Train on all but the last `test_months`, predict the held-out period.

    The PDF specifies backtesting on the last three years. For monthly data,
    test_months=36 implements that requirement.
    """
    df = _prepare_series(data, date_col, value_col)

    if test_months < 1:
        raise ValueError("test_months must be at least 1")
    if len(df) <= test_months:
        raise ValueError(
            f"Need more than {test_months} observations to backtest "
            "with this test window."
        )

    train = df.iloc[:-test_months].copy()
    test = df.iloc[-test_months:].copy()

    if len(train) < 24:
        raise ValueError(
            "Not enough training observations after reserving the test period. "
            "Use more historical data or a shorter test window."
        )

    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
    )
    model.fit(train)

    # Predict exactly the held-out dates, rather than relying on future dates.
    predicted = model.predict(test[["ds"]])
    comparison = pd.DataFrame({
        "date": test["ds"].dt.strftime("%Y-%m-%d"),
        "actual": test["y"].to_numpy(),
        "predicted": predicted["yhat"].to_numpy(),
    })
    comparison["absolute_error"] = (
        comparison["actual"] - comparison["predicted"]
    ).abs()

    mae = float(mean_absolute_error(comparison["actual"], comparison["predicted"]))

    return {
        "model": "Prophet",
        "test_months": test_months,
        "training_start": train["ds"].min().strftime("%Y-%m-%d"),
        "training_end": train["ds"].max().strftime("%Y-%m-%d"),
        "testing_start": test["ds"].min().strftime("%Y-%m-%d"),
        "testing_end": test["ds"].max().strftime("%Y-%m-%d"),
        "mae": mae,
        "mae_unit": "same unit as the input variable",
        "predictions": comparison.to_dict(orient="records"),
    }
