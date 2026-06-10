"""
OpenAI-compatible Chat Completions client for LLM-based assessment.

Provider priority (first available wins):
  1. OPENAI_API_KEY          → api.openai.com   (OpenAI)
  2. OPENROUTER_API_KEY      → openrouter.ai    (fallback, many free/cheap models)

Concurrency controls:
  - LLM_MAX_CONCURRENT (default 8): global threading.Semaphore limits simultaneous
    LLM calls so 50 concurrent users never exhaust the PG connection pool or
    trigger cascading timeouts.
  - LLM_MAX_RETRIES (default 3): exponential back-off on 429 / 503 before giving up.
  - LLM_RETRY_BASE_S (default 2): base sleep seconds between retries (doubles each time).

OpenRouter env vars:
  - OPENROUTER_API_KEY       → required to use OpenRouter
  - OPENROUTER_MODEL         → model slug (default: openai/gpt-4o-mini)
  - OPENROUTER_SITE_URL      → optional, sent as HTTP-Referer
  - OPENROUTER_SITE_NAME     → optional, sent as X-Title
"""
import logging
import os
import random
import threading
import time
from typing import Any, Dict, Generator, List, Optional, Union

_log = logging.getLogger(__name__)

_clients_lock = threading.Lock()
_primary_client = None   # first available provider client
_fallback_client = None  # OpenRouter client (used when primary is OpenAI and fails with 401)
_primary_provider = ""   # "openai" | "openrouter" | ""

# --- concurrency knobs (read once at module load) ---
_MAX_CONCURRENT: int = int(os.getenv("LLM_MAX_CONCURRENT", "8"))
_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "3"))
_RETRY_BASE_S: float = float(os.getenv("LLM_RETRY_BASE_S", "2.0"))

# Global semaphore: shared across ALL threads / workers in this process.
_llm_semaphore = threading.Semaphore(_MAX_CONCURRENT)

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# When using OpenRouter, default to a free model unless OPENROUTER_MODEL is set.
# Free models on OpenRouter have the ":free" suffix and require no credits.
# Default free model on OpenRouter (no credits needed).
# Override via OPENROUTER_MODEL env var if this slug becomes unavailable.
# Browse current free models at: https://openrouter.ai/models?q=:free
_OPENROUTER_DEFAULT_FREE_MODEL = "mistralai/mistral-7b-instruct:free"

_OPENROUTER_MODEL_REMAP = {
    "gpt-4o-mini":   _OPENROUTER_DEFAULT_FREE_MODEL,
    "gpt-4o":        _OPENROUTER_DEFAULT_FREE_MODEL,
    "gpt-4":         _OPENROUTER_DEFAULT_FREE_MODEL,
    "gpt-3.5-turbo": _OPENROUTER_DEFAULT_FREE_MODEL,
}


def _build_openrouter_client():
    """Build an OpenAI-SDK client pointed at OpenRouter. Returns None if key absent."""
    try:
        from openai import OpenAI
        key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not key:
            return None
        extra: Dict[str, str] = {}
        site_url = os.getenv("OPENROUTER_SITE_URL", "").strip()
        site_name = os.getenv("OPENROUTER_SITE_NAME", "SkillSight").strip()
        if site_url:
            extra["HTTP-Referer"] = site_url
        if site_name:
            extra["X-Title"] = site_name
        return OpenAI(
            api_key=key,
            base_url=_OPENROUTER_BASE_URL,
            default_headers=extra or None,
            max_retries=0,
        )
    except ImportError:
        return None


def _init_clients() -> None:
    """
    Initialise primary + fallback clients (called once, protected by _clients_lock).

    Priority:
      1. OPENAI_API_KEY  → primary=openai,    fallback=openrouter (if key also set)
      2. OPENROUTER_API_KEY only → primary=openrouter, fallback=None
    """
    global _primary_client, _fallback_client, _primary_provider
    try:
        from openai import OpenAI
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()

        if openai_key:
            _primary_client = OpenAI(api_key=openai_key, max_retries=0)
            _primary_provider = "openai"
            _log.info("LLM primary: openai")
            if openrouter_key:
                _fallback_client = _build_openrouter_client()
                _log.info("LLM fallback: openrouter (will activate on OpenAI 401/auth errors)")
        elif openrouter_key:
            _primary_client = _build_openrouter_client()
            _primary_provider = "openrouter"
            _log.info("LLM primary: openrouter (no OPENAI_API_KEY set)")
        # else: both absent → _primary_client stays None
    except ImportError:
        pass


def _get_client():
    """Return the primary LLM client, initialising it on first call."""
    global _primary_client
    if _primary_client is not None:
        return _primary_client
    with _clients_lock:
        if _primary_client is not None:
            return _primary_client
        _init_clients()
    return _primary_client


def _get_fallback_client():
    """Return the OpenRouter fallback client (or None if not configured)."""
    _get_client()  # ensure _init_clients has run
    return _fallback_client


def _is_auth_error(exc: Exception) -> bool:
    """Return True for 401/403 errors that indicate a bad/expired/quota-exceeded API key."""
    try:
        from openai import AuthenticationError, PermissionDeniedError
        if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
            return True
    except ImportError:
        pass
    msg = str(exc).lower()
    return (
        "401" in msg
        or "403" in msg
        or "incorrect api key" in msg
        or "authentication" in msg
        or "permission denied" in msg
        or "terms of service" in msg
    )


def _model_for_provider(requested_model: str, provider: str) -> str:
    """Map a model name to the right slug for the given provider."""
    if provider == "openrouter":
        override = os.getenv("OPENROUTER_MODEL", "").strip()
        if override:
            return override
        return _OPENROUTER_MODEL_REMAP.get(requested_model, requested_model)
    return requested_model


def _active_model(requested_model: str) -> str:
    """Return the model slug for the currently active primary provider."""
    _get_client()  # ensure init
    return _model_for_provider(requested_model, _primary_provider)


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


def _call_with_fallback(
    client,
    kwargs: Dict[str, Any],
    effective_model: str,
) -> str:
    """
    Call client.chat.completions.create with retry + automatic OpenRouter fallback.

    If the primary client returns 401 (invalid/expired key) and an OpenRouter
    fallback client is configured, transparently switch to OpenRouter for this
    call AND all subsequent calls in this process (re-pins the primary).
    """
    global _primary_client, _primary_provider

    last_exc: Exception | None = None
    with _llm_semaphore:
        for attempt in range(_MAX_RETRIES + 1):
            try:
                t0 = time.perf_counter()
                response = client.chat.completions.create(**kwargs)
                elapsed = time.perf_counter() - t0
                usage = getattr(response, "usage", None)
                _emit_llm_metric(
                    effective_model,
                    elapsed,
                    getattr(usage, "prompt_tokens", 0) or 0,
                    getattr(usage, "completion_tokens", 0) or 0,
                    attempt,
                    "ok",
                )
                if not response.choices:
                    return ""
                return response.choices[0].message.content or ""

            except Exception as exc:
                last_exc = exc

                # ── Auto-switch to OpenRouter on auth failure ──────────────
                if _is_auth_error(exc):
                    fb = _get_fallback_client()
                    if fb is not None and client is not fb:
                        _log.warning(
                            "Primary LLM returned auth error; switching to OpenRouter fallback. error=%s",
                            str(exc)[:120],
                        )
                        with _clients_lock:
                            _primary_client = fb
                            _primary_provider = "openrouter"
                        fb_model = _model_for_provider(
                            kwargs.get("model", "gpt-4o-mini"), "openrouter"
                        )
                        fb_kwargs = {**kwargs, "model": fb_model}
                        client = fb
                        kwargs = fb_kwargs
                        effective_model = fb_model
                        continue  # retry immediately with the new client
                    raise  # no fallback → surface the error

                is_rate_limit = _is_retryable(exc) and "429" in str(exc)
                status = "429" if is_rate_limit else "error"
                _emit_llm_metric(effective_model, 0.0, 0, 0, attempt, status)
                if attempt >= _MAX_RETRIES or not _is_retryable(exc):
                    raise
                sleep_s = _RETRY_BASE_S * (2 ** attempt) + random.uniform(0, 1)
                _log.warning("LLM retry attempt=%d/%d after %.1fs: %s",
                             attempt + 1, _MAX_RETRIES, sleep_s, exc)
                time.sleep(sleep_s)

    if last_exc is not None:
        raise last_exc
    return ""


def openai_generate(
    model: str,
    prompt: str,
    temperature: float = 0.0,
    timeout_s: int = 180,
    seed: int | None = None,
) -> str:
    """
    Call OpenAI-compatible Chat Completions API (non-stream, single prompt).
    Auto-falls back to OpenRouter when the primary key is invalid (401).
    Raises RuntimeError("llm_fallback_mode") when LLM_FALLBACK_RULES_ONLY=true.
    """
    if _is_fallback_only():
        raise RuntimeError("llm_fallback_mode")

    client = _get_client()
    if client is None:
        raise RuntimeError("LLM client unavailable: set OPENAI_API_KEY or OPENROUTER_API_KEY")

    effective_model = _active_model(model)
    timeout = min(timeout_s, 120)

    kwargs: Dict[str, Any] = {
        "model": effective_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "timeout": timeout,
    }
    if seed is not None:
        kwargs["seed"] = seed

    return _call_with_fallback(client, kwargs, effective_model)


def openai_chat(
    messages: List[Dict[str, Any]],
    model: str = "gpt-4o-mini",
    temperature: float = 0.3,
    stream: bool = False,
    timeout_s: int = 120,
) -> Union[str, Generator[str, None, None]]:
    """
    Multi-turn OpenAI-compatible Chat Completions (for tutor dialogue / RAG agent).

    - messages: list of {"role": "system"|"user"|"assistant", "content": str}.
    - stream=False: returns the final assistant message content (str).
    - stream=True: yields content chunks (generator).
    Auto-falls back to OpenRouter when the primary key is invalid (401).
    """
    if _is_fallback_only():
        raise RuntimeError("llm_fallback_mode")

    client = _get_client()
    if client is None:
        raise RuntimeError("LLM client unavailable: set OPENAI_API_KEY or OPENROUTER_API_KEY")

    effective_model = _active_model(model)
    timeout = min(timeout_s, 120)
    kwargs: Dict[str, Any] = {
        "model": effective_model,
        "messages": messages,
        "temperature": temperature,
        "timeout": timeout,
    }

    if stream:
        kwargs["stream"] = True
        return _openai_chat_stream(client, **kwargs)

    return _call_with_fallback(client, kwargs, effective_model)


def _openai_chat_stream(client, **kwargs) -> Generator[str, None, None]:
    stream = client.chat.completions.create(**kwargs)
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and getattr(delta, "content", None):
            yield delta.content
