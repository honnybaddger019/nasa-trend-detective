"""Stand-in for the team's server.py, used to test the Role 6 kit end to end.

It is NOT the real backend: the statistics are fixed demo values. It shows
exactly how Member 4 plugs the security layer into server.py:

    from security import install_security, limit_llm, limit_compute, ...
    install_security(app)                          # once, after app = FastAPI()
    @limit_llm / @limit_compute                    # under each route decorator

Run:  uvicorn examples.demo_server:app --port 8000
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from llm_client import LLMClient
from security import (
    AnalyzeRequest,
    AskRequest,
    guarded_ask,
    guarded_explain,
    install_security,
    limit_compute,
    limit_llm,
    request_id_of,
)

app = FastAPI(title="EarthTrend AI - Role 6 demo backend")
install_security(app)
llm = LLMClient.from_env()

# Member 4 owns the real prompt wording; the guard is appended by security.py.
MEMBER4_PROMPT = (
    "You are an environmental data analyst. Using ONLY the numbers provided, explain the "
    "results in simple language. Say 'the data shows', never claim causes, and mention "
    "the forecast error."
)


def compute_stats(body: AnalyzeRequest) -> dict[str, Any]:
    """Demo values. In the real app: Member 2 data + Member 3 stats + Member 4 models."""
    return {
        "data_source": "NASA POWER (demo values, not a real analysis)",
        "region": {"lat": body.lat, "lon": body.lon},
        "variable": body.variable,
        "period": {"start": body.start, "end": body.end},
        "trend_per_decade": 0.42,
        "mann_kendall_p_value": 0.003,
        "anomalies": [{"month": f"{body.end - 2}-07", "z_score": 2.8}],
        "forecast": {"horizon_years": 3, "backtest_mae": 0.31},
    }


def fallback_text(stats: dict[str, Any]) -> str:
    """Member 4's template text, used when the LLM is unavailable."""
    return (
        f"The data shows a trend of {stats['trend_per_decade']} per decade between "
        f"{stats['period']['start']} and {stats['period']['end']} "
        f"(Mann-Kendall p-value {stats['mann_kendall_p_value']}). "
        f"Forecast error (MAE): {stats['forecast']['backtest_mae']}."
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index() -> str:
    return "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>EarthTrend AI</title></head><body><h1>EarthTrend AI demo backend</h1></body></html>"


@app.post("/analyze")
@limit_compute
async def analyze(request: Request, body: AnalyzeRequest) -> dict[str, Any]:
    return compute_stats(body)


@app.post("/explain")
@limit_llm
async def explain(request: Request, body: AnalyzeRequest) -> dict[str, str]:
    stats = compute_stats(body)
    return await guarded_explain(
        llm, base_system_prompt=MEMBER4_PROMPT, stats=stats,
        fallback_text=fallback_text(stats), request_id=request_id_of(request),
    )


@app.post("/ask")
@limit_llm
async def ask(request: Request, body: AskRequest) -> dict[str, str]:
    stats = compute_stats(body)  # recomputed on the server, never sent by the browser
    return await guarded_ask(
        llm, base_system_prompt=MEMBER4_PROMPT, stats=stats, question=body.question,
        fallback_text=fallback_text(stats), request_id=request_id_of(request),
    )
