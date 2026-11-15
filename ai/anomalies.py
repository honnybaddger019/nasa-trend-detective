"""Anomaly detection for monthly environmental time series.

The PDF recommends removing trend and seasonality before applying
Isolation Forest. STL decomposition is used to estimate the trend and
seasonal components; Isolation Forest is applied to the residuals.
"""

from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from statsmodels.tsa.seasonal import STL


def detectAnomalies(
    data: pd.DataFrame,
    date_col: str = "date",
    value_col: str = "value",
    contamination: float | str = "auto",
    random_state: int = 42,
) -> dict[str, Any]:
    """Detect unusual monthly observations using STL + Isolation Forest.

    `contamination` can be "auto" or a float between 0 and 0.5.
    For monthly data, at least 24 observations are recommended.
    """
    if not isinstance(data, pd.DataFrame):
        raise TypeError("data must be a pandas DataFrame")

    missing = [col for col in (date_col, value_col) if col not in data.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = data[[date_col, value_col]].copy()
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna().sort_values("date")
    df = df.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)

    if len(df) < 24:
        raise ValueError(
            "At least 24 monthly observations are required for STL "
            "seasonal decomposition."
        )
    if contamination != "auto":
        if not isinstance(contamination, (int, float)) or not 0 < contamination <= 0.5:
            raise ValueError("contamination must be 'auto' or a float in (0, 0.5].")

    # STL works best with a regular monthly series. Reindex to month-start dates.
    df = df.set_index("date").asfreq("MS")
    if df["value"].isna().any():
        raise ValueError(
            "The monthly series has missing months. Fill or interpolate missing "
            "monthly values before anomaly detection."
        )

    stl = STL(df["value"], period=12, robust=True)
    decomposition = stl.fit()
    residuals = decomposition.resid.to_numpy().reshape(-1, 1)

    detector = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        random_state=random_state,
    )
    labels = detector.fit_predict(residuals)
    scores = detector.decision_function(residuals)

    result = pd.DataFrame({
        "date": df.index.strftime("%Y-%m-%d"),
        "value": df["value"].to_numpy(),
        "trend": decomposition.trend.to_numpy(),
        "seasonal": decomposition.seasonal.to_numpy(),
        "residual": decomposition.resid.to_numpy(),
        "anomaly": labels == -1,
        "anomaly_score": scores,
    })

    anomalies = result[result["anomaly"]].copy()
    anomalies = anomalies.replace({np.nan: None})

    return {
        "method": "STL decomposition + Isolation Forest",
        "observations": int(len(result)),
        "anomaly_count": int(len(anomalies)),
        "anomalies": anomalies.to_dict(orient="records"),
        "all_observations": result.replace({np.nan: None}).to_dict(orient="records"),
        "note": (
            "An anomaly is a statistically unusual observation, not proof of a "
            "heatwave, drought, or its cause. Verify it against context and sources."
        ),
    }
