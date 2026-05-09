"""
OpenAI Chat Completions client for LLM-based assessment.
Used when LLM_PROVIDER=openai; requires OPENAI_API_KEY.

Concurrency controls:
  - LLM_MAX_CONCURRENT (default 8): global threading.Semaphore limits simultaneous
    OpenAI calls so 50 concurrent users never exhaust the PG connection pool or
    trigger cascading timeouts.
  - LLM_MAX_RETRIES (default 3): exponential back-off on 429 / 503 before giving up.
  - LLM_RETRY_BASE_S (default 2): base sleep seconds between retries (doubles each time).
"""
import logging
import os
import random
import threading
import time
from typing import Any, Dict, Generator, List, Optional, Union

_log = logging.getLogger(__name__)

_openai_client = None
_openai_client_lock = threading.Lock()

# --- concurrency knobs (read once at module load) ---
_MAX_CONCURRENT: int = int(os.getenv("LLM_MAX_CONCURRENT", "8"))
_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "3"))
_RETRY_BASE_S: float = float(os.getenv("LLM_RETRY_BASE_S", "2.0"))

# Global semaphore: shared across ALL threads / workers in this process.
_llm_semaphore = threading.Semaphore(_MAX_CONCURRENT)


def _get_client():
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    with _openai_client_lock:
        if _openai_client is not None:
            return _openai_client
        try:
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                return None
            _openai_client = OpenAI(
                api_key=api_key,
                max_retries=0,  # we do our own retry with back-off
            )
        except ImportError:
            return None
    return _openai_client


def _is_retryable(exc: Exception) -> bool:
    """Return True for rate-limit (429) or transient server (5xx) errors."""
    try:
        from openai import RateLimitError, APIStatusError
        if isinstance(exc, RateLimitError):
            return True
        if isinstance(exc, APIStatusError) and exc.status_code in (429, 500, 502, 503, 504):
            return True
    except ImportError:
        pass
    msg = str(exc).lower()
    return any(k in msg for k in ("rate limit", "429", "503", "502", "timeout"))


def _is_fallback_only() -> bool:
    """Return True when LLM_FALLBACK_RULES_ONLY=true so callers skip LLM entirely."""
    val = os.getenv("LLM_FALLBACK_RULES_ONLY", "").strip().lower()
    return val in ("1", "true", "yes", "on")


def _emit_llm_metric(
    model: str,
    elapsed_s: float,
    prompt_tokens: int,
    completion_tokens: int,
    attempt: int,
    status: str,  # "ok" | "429" | "error"
) -> None:
    """Structured log line consumed by monitoring / log-based metrics."""
    _log.info(
        "llm.metric model=%s status=%s elapsed_s=%.2f prompt_tokens=%d completion_tokens=%d "
        "total_tokens=%d attempt=%d",
        model,
        status,
        elapsed_s,
        prompt_tokens,
        completion_tokens,
        prompt_tokens + completion_tokens,
        attempt,
    )


def openai_generate(
    model: str,
    prompt: str,
    temperature: float = 0.0,
    timeout_s: int = 180,
    seed: int | None = None,
) -> str:
    """
    Call OpenAI Chat Completions API (non-stream).
    Acquires a global semaphore so at most LLM_MAX_CONCURRENT calls run in parallel.
    Retries up to LLM_MAX_RETRIES times on 429 / 503 with exponential back-off + jitter.
    Emits structured llm.metric log lines for observability.
    Returns the assistant message content as a string.
    Raises RuntimeError("llm_fallback_mode") when LLM_FALLBACK_RULES_ONLY=true.
    """
    if _is_fallback_only():
        raise RuntimeError("llm_fallback_mode")

    client = _get_client()
    if client is None:
        raise RuntimeError("OpenAI client not available (missing openai package or OPENAI_API_KEY)")

    timeout = min(timeout_s, 120)

    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "timeout": timeout,
    }
    if seed is not None:
        kwargs["seed"] = seed

    last_exc: Exception | None = None
    with _llm_semaphore:
        for attempt in range(_MAX_RETRIES + 1):
            try:
                t0 = time.perf_counter()
                response = client.chat.completions.create(**kwargs)
                elapsed = time.perf_counter() - t0
                usage = getattr(response, "usage", None)
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                _emit_llm_metric(model, elapsed, prompt_tokens, completion_tokens, attempt, "ok")
                if not response.choices:
                    return ""
                content = response.choices[0].message.content
                return content or ""
            except Exception as exc:
                last_exc = exc
                is_rate_limit = _is_retryable(exc) and "429" in str(exc)
                status = "429" if is_rate_limit else "error"
                _emit_llm_metric(model, 0.0, 0, 0, attempt, status)
                if attempt >= _MAX_RETRIES or not _is_retryable(exc):
                    raise
                sleep_s = _RETRY_BASE_S * (2 ** attempt) + random.uniform(0, 1)
                _log.warning(
                    "openai_generate retry attempt=%d/%d after %.1fs: %s",
                    attempt + 1, _MAX_RETRIES, sleep_s, exc,
                )
                time.sleep(sleep_s)

    if last_exc is not None:
        raise last_exc
    return ""


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
    Acquires the global LLM semaphore for non-streaming calls.
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

    if _is_fallback_only():
        raise RuntimeError("llm_fallback_mode")

    if stream:
        kwargs["stream"] = True
        return _openai_chat_stream(client, **kwargs)

    last_exc: Exception | None = None
    with _llm_semaphore:
        for attempt in range(_MAX_RETRIES + 1):
            try:
                t0 = time.perf_counter()
                response = client.chat.completions.create(**kwargs)
                elapsed = time.perf_counter() - t0
                usage = getattr(response, "usage", None)
                _emit_llm_metric(
                    model,
                    elapsed,
                    getattr(usage, "prompt_tokens", 0) or 0,
                    getattr(usage, "completion_tokens", 0) or 0,
                    attempt,
                    "ok",
                )
                if not response.choices:
                    return ""
                content = response.choices[0].message.content
                return content or ""
            except Exception as exc:
                last_exc = exc
                status = "429" if (_is_retryable(exc) and "429" in str(exc)) else "error"
                _emit_llm_metric(model, 0.0, 0, 0, attempt, status)
                if attempt >= _MAX_RETRIES or not _is_retryable(exc):
                    raise
                sleep_s = _RETRY_BASE_S * (2 ** attempt) + random.uniform(0, 1)
                _log.warning("openai_chat retry attempt=%d/%d: %s", attempt + 1, _MAX_RETRIES, exc)
                time.sleep(sleep_s)
    if last_exc is not None:
        raise last_exc
    return ""


def _openai_chat_stream(client, **kwargs) -> Generator[str, None, None]:
    stream = client.chat.completions.create(**kwargs)
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and getattr(delta, "content", None):
            yield delta.content
