"""
Shared utilities for email tools.
"""

import os
import structlog
import tenacity
import sentry_sdk

# PDF text extraction
from pypdf import PdfReader

logger = structlog.get_logger()


@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
    stop=tenacity.stop_after_attempt(3),
    reraise=True,
    before_sleep=lambda rs: logger.warning("email_llm.retry", attempt=rs.attempt_number),
)
def _call_llm(prompt: str) -> str:
    """Helper: call DeepSeek via LiteLLM and return the response text."""
    import litellm
    model = os.getenv("LLM_MODEL", "deepseek/deepseek-v4-flash")
    api_key = os.getenv("DEEPSEEK_API_KEY")
    with sentry_sdk.start_span(op="llm", description="email._call_llm"):
        resp = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            api_key=api_key,
            timeout=30,
        )
    return resp.choices[0].message.content.strip()