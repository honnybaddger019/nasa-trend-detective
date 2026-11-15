
"""LLM explanation and question-answering using Groq."""

from __future__ import annotations

import json
import os
from typing import Any
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

def _fallback_explanation(stats: dict[str, Any]) -> str:
    """Provide a safe explanation if the Groq API is unavailable."""

    region = stats.get("region", "the selected region")
    variable = stats.get("variable", "the selected environmental variable")
    trend = stats.get("trend", "not provided")
    p_value = stats.get("p_value", "not provided")
    mae = stats.get("forecast_mae", "not provided")

    return (
        f"For {region}, the reported {variable} trend is: {trend}. "
        f"The reported p-value is {p_value}, and the forecast MAE is {mae}. "
        "These results describe patterns in the supplied data; they do not "
        "establish the cause of the changes. Interpret forecasts and detected "
        "anomalies with their uncertainty and data limitations in mind."
    )


def _get_groq_client() -> Groq | None:
    """Create a Groq client if the API key is configured."""

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        return None

    return Groq(api_key=api_key)


def _generate_response(
    prompt: str,
    max_tokens: int = 500,
) -> str | None:
    """Send a prompt to Groq and return the generated text."""

    try:
        client = _get_groq_client()

        if client is None:
            return None

        model_name = os.getenv(
            "GROQ_MODEL",
            "openai/gpt-oss-20b"
        )

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0,
            max_tokens=max_tokens,
        )

        answer = response.choices[0].message.content

        return answer.strip() if answer else None

    except Exception:
        # Do not expose API keys or internal errors.
        return None


def explain(
    stats: dict[str, Any],
    language: str = "English",
) -> str:
    """Generate a short, cautious environmental data explanation."""

    if not isinstance(stats, dict):
        raise TypeError("stats must be a dictionary")

    prompt = f"""
You are an environmental data analyst.

Write a short explanation in {language} using ONLY the supplied JSON data.

Rules:
- Do not invent facts, numbers, events, or causes.
- Say "the data shows" rather than claiming why a change happened.
- Explain statistical significance only if a p-value is supplied.
- Mention forecast error if it is supplied.
- Explain that anomalies are statistical flags, not proof of a real-world event.
- Mention limitations or uncertainty where relevant.
- If a field is missing, say it was not provided.
- Keep the explanation understandable to a non-specialist.

Computed results:

{json.dumps(stats, ensure_ascii=False, default=str)}
"""

    result = _generate_response(prompt, max_tokens=500)

    if result:
        return result

    return _fallback_explanation(stats)


def ask_data(
    question: str,
    computed_results: dict[str, Any],
    language: str = "English",
) -> str:
    """Answer a question using only computed environmental results."""

    if not question.strip():
        raise ValueError("question cannot be empty")

    if not isinstance(computed_results, dict):
        raise TypeError("computed_results must be a dictionary")

    prompt = f"""
You are an assistant for an environmental data dashboard.

Answer the user's question in {language} using ONLY the computed JSON below.

Rules:
- Do not invent values, events, explanations, or causes.
- Never use external information.
- If the JSON does not contain enough information, say so clearly.
- Give a short and understandable answer.

Computed results:

{json.dumps(computed_results, ensure_ascii=False, default=str)}

User question:

{question}
"""

    result = _generate_response(prompt, max_tokens=400)

    if result:
        return result

    return (
        "The Ask the Data service is temporarily unavailable. "
        "Please check the Groq API configuration."
    )
