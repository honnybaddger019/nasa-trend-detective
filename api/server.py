"""FastAPI backend for Member 4's forecasting, anomalies, and LLM features.

Run from the project root:
    uvicorn api.server:app --reload
"""

from __future__ import annotations

from typing import Any
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ai.forecasting import forecast, backtest
from ai.anomalies import detectAnomalies
from ai.explanation import explain, ask_data

app = FastAPI(
    title="EarthTrend AI - Member 4 API",
    description="Forecasting, anomaly detection, and AI explanations.",
    version="1.0.0",
)


class TimeSeriesRequest(BaseModel):
    data: list[dict[str, Any]] = Field(
        ...,
        description='List of rows such as [{"date":"2020-01-01","value":18.2}]',
        min_length=24,
    )
    date_col: str = "date"
    value_col: str = "value"


class ForecastRequest(TimeSeriesRequest):
    periods: int = Field(default=36, ge=1, le=60)
    interval_width: float = Field(default=0.95, gt=0, lt=1)


class BacktestRequest(TimeSeriesRequest):
    test_months: int = Field(default=36, ge=1, le=60)


class AnomalyRequest(TimeSeriesRequest):
    contamination: str | float = "auto"


class ExplainRequest(BaseModel):
    stats: dict[str, Any]
    language: str = "English"


class AskDataRequest(BaseModel):
    question: str
    computed_results: dict[str, Any]
    language: str = "English"


def _dataframe(request: TimeSeriesRequest) -> pd.DataFrame:
    return pd.DataFrame(request.data)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "EarthTrend AI Member 4"}


@app.post("/forecast")
def forecast_endpoint(request: ForecastRequest) -> dict[str, Any]:
    try:
        return forecast(
            _dataframe(request),
            periods=request.periods,
            date_col=request.date_col,
            value_col=request.value_col,
            interval_width=request.interval_width,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Forecasting failed.") from exc


@app.post("/backtest")
def backtest_endpoint(request: BacktestRequest) -> dict[str, Any]:
    try:
        return backtest(
            _dataframe(request),
            test_months=request.test_months,
            date_col=request.date_col,
            value_col=request.value_col,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Backtesting failed.") from exc


@app.post("/anomalies")
def anomalies_endpoint(request: AnomalyRequest) -> dict[str, Any]:
    try:
        contamination: str | float = request.contamination
        if isinstance(contamination, str) and contamination != "auto":
            try:
                contamination = float(contamination)
            except ValueError as exc:
                raise ValueError("contamination must be 'auto' or a number.") from exc

        return detectAnomalies(
            _dataframe(request),
            date_col=request.date_col,
            value_col=request.value_col,
            contamination=contamination,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Anomaly detection failed.") from exc


@app.post("/explain")
def explain_endpoint(request: ExplainRequest) -> dict[str, str]:
    return {
        "explanation": explain(request.stats, language=request.language)
    }


@app.post("/ask")
def ask_endpoint(request: AskDataRequest) -> dict[str, str]:
    try:
        return {
            "answer": ask_data(
                request.question,
                request.computed_results,
                language=request.language,
            )
        }
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
