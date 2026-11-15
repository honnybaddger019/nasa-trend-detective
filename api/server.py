"""FastAPI backend for Member 4's forecasting, anomalies, and LLM features.

Run from the project root:
    uvicorn api.server:app --reload

Security layer (Role 6, see SECURITY.md and docs/threat-model.md):
- install_security(): security headers, CORS, body size limit, request IDs,
  generic error messages, JSON logs and the /health route.
- Rate limits: @limit_compute on the CPU-heavy routes, @limit_llm on the AI routes.
- Strict, bounded request models: unknown fields, oversized series, NaN or
  infinite numbers and unknown languages are rejected with 422.
- Prompt-injection guard on /ask and on every text sent to the LLM
  (OWASP Top 10 for LLM Applications, LLM01), output filter on AI answers.

The route names and response keys of Member 4 are unchanged. Every rate-limited
route takes `request: Request`, so the JSON body parameter is called `body`.

AI-assisted code: the security integration in this file was written with an AI coding
assistant (Claude Code), then reviewed and tested by Role 6 (see README, "Use of AI tools").
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from ai.anomalies import detectAnomalies
from ai.explanation import ask_data, explain
from ai.forecasting import backtest, forecast
from security import (
    REFUSAL_MESSAGE,
    check_output,
    find_injection,
    install_security,
    limit_compute,
    limit_llm,
    log_event,
    normalize_question,
    request_id_of,
    settings,
)

app = FastAPI(
    title="EarthTrend AI - Member 4 API",
    description="Forecasting, anomaly detection, and AI explanations.",
    version="1.0.0",
)
install_security(app)  # also adds GET /health

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True)

MAX_ROWS = 1200  # 100 years of monthly values
MAX_CONTEXT_ITEMS = 200  # keys + list items in a stats dict sent to the LLM
MAX_CONTEXT_DEPTH = 4
MAX_CONTEXT_TEXT = 200  # characters per text value sent to the LLM
FALLBACK_MESSAGE = "The AI explanation is not available right now. The charts and statistics are still valid."

ColumnName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,31}$")]
CellValue = Annotated[str, StringConstraints(max_length=32)] | float | int | None
Language = Literal["English", "French", "Arabic", "Spanish"]


def _reject_bad_numbers(value: Any, depth: int = 0) -> Any:
    """Reject NaN / infinity and booleans used as numbers, anywhere in a payload."""
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        raise ValueError("numbers must be finite")
    if isinstance(value, dict):
        for item in value.values():
            _reject_bad_numbers(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _reject_bad_numbers(item, depth + 1)
    return value


def _check_llm_context(value: Any) -> dict[str, Any]:
    """Bound a dict that goes into the LLM prompt and scan its text for injection.

    The browser sends these statistics, so every key and text value is untrusted:
    it is limited in size and depth, and a value that looks like an instruction
    to the model is rejected (422) before any LLM call.
    """
    if not isinstance(value, dict):
        raise ValueError("must be an object")
    count = 0

    def walk(node: Any, depth: int) -> None:
        nonlocal count
        if depth > MAX_CONTEXT_DEPTH:
            raise ValueError("too deeply nested")
        if isinstance(node, dict):
            for key, item in node.items():
                count += 1
                if not isinstance(key, str) or len(key) > 64:
                    raise ValueError("keys must be short strings")
                walk(key, depth + 1)  # keys reach the prompt too: same text checks
                walk(item, depth + 1)
        elif isinstance(node, list):
            count += len(node)
            for item in node:
                walk(item, depth + 1)
        elif isinstance(node, str):
            if len(node) > MAX_CONTEXT_TEXT:
                raise ValueError("text values are too long")
            if find_injection(node) is not None:
                raise ValueError("text values must be data, not instructions")
        elif isinstance(node, bool) or node is None or isinstance(node, (int, float)):
            _reject_bad_numbers(node)
        else:
            raise ValueError("unsupported value type")
        if count > MAX_CONTEXT_ITEMS:
            raise ValueError("too many values")

    walk(value, 0)
    return value


class TimeSeriesRequest(BaseModel):
    model_config = _STRICT

    data: list[dict[ColumnName, CellValue]] = Field(
        ...,
        description='List of rows such as [{"date":"2020-01-01","value":18.2}]',
        min_length=24,
        max_length=MAX_ROWS,
    )
    date_col: ColumnName = "date"
    value_col: ColumnName = "value"

    _numbers = field_validator("data")(_reject_bad_numbers)


class ForecastRequest(TimeSeriesRequest):
    periods: int = Field(default=36, ge=1, le=60)
    interval_width: float = Field(default=0.95, gt=0, lt=1, allow_inf_nan=False)


class BacktestRequest(TimeSeriesRequest):
    test_months: int = Field(default=36, ge=1, le=60)


class AnomalyRequest(TimeSeriesRequest):
    # IsolationForest accepts "auto" or a share of outliers in (0, 0.5].
    contamination: Literal["auto"] | Annotated[float, Field(gt=0, le=0.5, allow_inf_nan=False)] = "auto"


class ExplainRequest(BaseModel):
    model_config = _STRICT

    stats: dict[str, Any]
    language: Language = "English"

    _stats = field_validator("stats", mode="before")(_check_llm_context)


class AskDataRequest(BaseModel):
    model_config = _STRICT

    question: str = Field(min_length=1, max_length=settings.question_max_chars * 2)
    computed_results: dict[str, Any]
    language: Language = "English"

    _results = field_validator("computed_results", mode="before")(_check_llm_context)

    @field_validator("question")
    @classmethod
    def _check_question(cls, value: str) -> str:
        cleaned = normalize_question(value)
        if len(cleaned) < settings.question_min_chars:
            raise ValueError(f"the question must contain at least {settings.question_min_chars} characters")
        if len(cleaned) > settings.question_max_chars:
            raise ValueError(f"the question must contain at most {settings.question_max_chars} characters")
        return cleaned


def _dataframe(body: TimeSeriesRequest) -> pd.DataFrame:
    return pd.DataFrame(body.data)


def _client_error(exc: Exception) -> HTTPException:
    # Messages of Member 4's own checks ("not enough data", ...). Capped so a
    # message can never carry a large part of the submitted data back.
    return HTTPException(status_code=400, detail=str(exc)[:200] or "Invalid input.")


def _safe_answer(text: Any, request: Request, route: str) -> str:
    """Layer 4 of the guard: plain text, bounded, no leaked instructions."""
    answer = check_output(text if isinstance(text, str) else None)
    if answer is None:
        log_event("llm_fallback", logging.WARNING, reason="empty_output", route=route,
                  request_id=request_id_of(request))
        return FALLBACK_MESSAGE
    return answer


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.post("/forecast")
@limit_compute
def forecast_endpoint(request: Request, body: ForecastRequest) -> dict[str, Any]:
    try:
        return forecast(
            _dataframe(body),
            periods=body.periods,
            date_col=body.date_col,
            value_col=body.value_col,
            interval_width=body.interval_width,
        )
    except (ValueError, TypeError) as exc:
        raise _client_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Forecasting failed.") from exc


@app.post("/backtest")
@limit_compute
def backtest_endpoint(request: Request, body: BacktestRequest) -> dict[str, Any]:
    try:
        return backtest(
            _dataframe(body),
            test_months=body.test_months,
            date_col=body.date_col,
            value_col=body.value_col,
        )
    except (ValueError, TypeError) as exc:
        raise _client_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Backtesting failed.") from exc


@app.post("/anomalies")
@limit_compute
def anomalies_endpoint(request: Request, body: AnomalyRequest) -> dict[str, Any]:
    try:
        return detectAnomalies(
            _dataframe(body),
            date_col=body.date_col,
            value_col=body.value_col,
            contamination=body.contamination,
        )
    except (ValueError, TypeError) as exc:
        raise _client_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Anomaly detection failed.") from exc


@app.post("/explain")
@limit_llm
def explain_endpoint(request: Request, body: ExplainRequest) -> dict[str, str]:
    try:
        text = explain(body.stats, language=body.language)
    except Exception as exc:  # provider down, quota exceeded, timeout: never a 500
        log_event("llm_fallback", logging.WARNING, reason=type(exc).__name__, route="/explain",
                  request_id=request_id_of(request))
        return {"explanation": FALLBACK_MESSAGE, "source": "fallback"}
    return {"explanation": _safe_answer(text, request, "/explain"), "source": "llm"}


@app.post("/ask")
@limit_llm
def ask_endpoint(request: Request, body: AskDataRequest) -> dict[str, str]:
    rule = find_injection(body.question)
    if rule is not None:
        log_event("prompt_injection_blocked", logging.WARNING, rule=rule,
                  question_chars=len(body.question), request_id=request_id_of(request))
        return {"answer": REFUSAL_MESSAGE, "source": "guard"}
    try:
        text = ask_data(body.question, body.computed_results, language=body.language)
    except (ValueError, TypeError) as exc:
        raise _client_error(exc) from exc
    except Exception as exc:
        log_event("llm_fallback", logging.WARNING, reason=type(exc).__name__, route="/ask",
                  request_id=request_id_of(request))
        return {"answer": FALLBACK_MESSAGE, "source": "fallback"}
    return {"answer": _safe_answer(text, request, "/ask"), "source": "llm"}
