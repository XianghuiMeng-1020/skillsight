"""
OpenAI Chat Completions client for LLM-based assessment.
Used when LLM_PROVIDER=openai; requires OPENAI_API_KEY.
"""
import os
from typing import Optional

_openai_client = None


def _get_client():
    global _openai_client
    if _openai_client is None:
        try:
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                return None
            _openai_client = OpenAI(api_key=api_key)
        except ImportError:
            return None
    return _openai_client


def openai_generate(
    model: str,
    prompt: str,
    temperature: float = 0.0,
    timeout_s: int = 180,
) -> str:
    """
    Call OpenAI Chat Completions API (non-stream).
    Returns the assistant message content as a string.
    """
    client = _get_client()
    if client is None:
        raise RuntimeError("OpenAI client not available (missing openai package or OPENAI_API_KEY)")

    # OpenAI uses different param name; cap timeout for API
    timeout = min(timeout_s, 120)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        timeout=timeout,
    )
    if not response.choices:
        return ""
    content = response.choices[0].message.content
    return content or ""
