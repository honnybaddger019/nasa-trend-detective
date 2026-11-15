"""Snippet for Member 4 - calling the LLM through the Role 6 guard.

Member 4 keeps the prompt wording (MEMBER4_PROMPT) and the fallback template.
security.py adds the 4 defence layers around them:
  1. input filter (known attack patterns, base64, length 3-300),
  2. structure: instructions only in the system prompt, data in <stats>,
     question in <question>, both escaped,
  3. context: only the computed stats dict is sent - no key, no tool,
  4. output: capped tokens, instruction-leak detector, HTML removed,
     fallback text on any provider error.

The provider is chosen with environment variables (LLM_PROVIDER, LLM_MODEL,
LLM_API_KEY): no code change when the free offer is known.
"""

from typing import Any

from fastapi import Request

from llm_client import LLMClient
from security import AskRequest, guarded_ask, limit_llm, request_id_of

llm = LLMClient.from_env()  # create ONCE at startup, not per request

MEMBER4_PROMPT = "..."  # Member 4's honest-analyst prompt


def compute_stats(body: AskRequest) -> dict[str, Any]: ...      # Members 2-4
def fallback_text(stats: dict[str, Any]) -> str: ...            # Member 4


# In server.py:
# @app.post("/ask")
# @limit_llm
async def ask(request: Request, body: AskRequest) -> dict[str, str]:
    stats = compute_stats(body)
    return await guarded_ask(
        llm,
        base_system_prompt=MEMBER4_PROMPT,
        stats=stats,
        question=body.question,
        fallback_text=fallback_text(stats),
        request_id=request_id_of(request),
    )
    # Returns {"answer": "...", "source": "llm" | "guard" | "fallback"}.
    # Front end (Member 5): display "answer" with element.textContent, never innerHTML.
