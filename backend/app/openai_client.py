"""
OpenAI Chat Completions client for LLM-based assessment.
Used when LLM_PROVIDER=openai; requires OPENAI_API_KEY.
"""
import os
from typing import Any, Dict, Generator, List, Optional, Union

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


def openai_chat(
    messages: List[Dict[str, Any]],
    model: str = "gpt-4o-mini",
    temperature: float = 0.3,
    stream: bool = False,
    timeout_s: int = 120,
) -> Union[str, Generator[str, None, None]]:
    """
    Multi-turn OpenAI Chat Completions (for tutor dialogue / RAG agent).

    - messages: list of {"role": "system"|"user"|"assistant", "content": str}.
    - stream=False: returns the final assistant message content (str).
    - stream=True: yields content chunks (generator).
    """
    client = _get_client()
    if client is None:
        raise RuntimeError("OpenAI client not available (missing openai package or OPENAI_API_KEY)")

    timeout = min(timeout_s, 120)
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "timeout": timeout,
    }

    if stream:
        kwargs["stream"] = True
        return _openai_chat_stream(client, **kwargs)
    response = client.chat.completions.create(**kwargs)
    if not response.choices:
        return ""
    content = response.choices[0].message.content
    return content or ""


def _openai_chat_stream(client, **kwargs) -> Generator[str, None, None]:
    stream = client.chat.completions.create(**kwargs)
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and getattr(delta, "content", None):
            yield delta.content
