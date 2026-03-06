"""
Rate limiting: Redis-backed when available, in-memory fallback for dev.
Config via ENV: RATE_LIMIT_ENABLED, RATE_LIMIT_PER_MINUTE_*.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from threading import Lock
from typing import Optional

# Path prefixes that get rate limited (each has its own bucket)
RATE_LIMIT_SCOPES = {
    "auth": "/auth/",
    "documents_upload": "/documents/upload",
    "documents_import": "/documents/import",
    "ai": "/ai/",
    "search": "/search/",
    "assess": "/assess/",
    "interactive": "/interactive/",
    "roles_import": "/roles/import",
    "skills_import": "/skills/import",
}

# In-memory fallback: scope -> (client_key -> (count, window_start))
_memory: dict[str, dict[str, tuple[int, float]]] = defaultdict(dict)
_memory_lock = Lock()
_WINDOW_SECONDS = 60


def _parse_bool_env(key: str, default: bool = False) -> bool:
    """Parse env var as bool.

    Truthy:  '1', 'true', 'yes', 'on'  (case-insensitive)
    Falsy:   '0', 'false', 'no', 'off', '' (or key absent)
    """
    val = os.getenv(key, "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off", ""):
        return False
    return default


def _is_enabled() -> bool:
    return _parse_bool_env("RATE_LIMIT_ENABLED")


def _scope_for_path(path: str) -> Optional[str]:
    if path.startswith("/auth/"):
        return "auth"
    if path.startswith("/documents/upload"):
        return "documents_upload"
    if path.startswith("/documents/import"):
        return "documents_import"
    if path.startswith("/ai/"):
        return "ai"
    if path.startswith("/search/"):
        return "search"
    if path.startswith("/assess/"):
        return "assess"
    if path.startswith("/interactive/"):
        return "interactive"
    if path.startswith("/roles/import"):
        return "roles_import"
    if path.startswith("/skills/import"):
        return "skills_import"
    return None


def _limit_for_scope(scope: str) -> int:
    env_map = {
        "auth": "RATE_LIMIT_PER_MINUTE_AUTH",
        "documents_upload": "RATE_LIMIT_PER_MINUTE_UPLOAD",
        "documents_import": "RATE_LIMIT_PER_MINUTE_UPLOAD",  # same as upload
        "ai": "RATE_LIMIT_PER_MINUTE_AI",
        "search": "RATE_LIMIT_PER_MINUTE_SEARCH",
        "assess": "RATE_LIMIT_PER_MINUTE_ASSESS",
        "interactive": "RATE_LIMIT_PER_MINUTE_INTERACTIVE",
        "roles_import": "RATE_LIMIT_PER_MINUTE_IMPORT",
        "skills_import": "RATE_LIMIT_PER_MINUTE_IMPORT",
    }
    key = env_map.get(scope, "RATE_LIMIT_PER_MINUTE")
    default = 60
    return int(os.getenv(key, os.getenv("RATE_LIMIT_PER_MINUTE", str(default))))


def _client_key(request_scope: dict) -> str:
    """Stable key for the client: IP address only (never includes the ephemeral source port)."""
    # Prefer headers set by reverse proxy
    headers = request_scope.get("headers") or []
    for k, v in headers:
        if k.lower() == b"x-forwarded-for":
            return (v.decode("utf-8") if isinstance(v, bytes) else v).split(",")[0].strip()
        if k.lower() == b"x-real-ip":
            return v.decode("utf-8") if isinstance(v, bytes) else v
    client = request_scope.get("client")
    if client:
        # client is (host, port) — use only the host so all requests from the
        # same IP share one bucket regardless of ephemeral source port.
        return str(client[0])
    return "unknown"


def _redis_incr(scope: str, client_key: str, limit: int) -> Optional[tuple[bool, int]]:
    """Returns (allowed, current_count) or None if Redis unavailable."""
    try:
        import redis
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        r = redis.Redis(host=host, port=port, db=0, socket_connect_timeout=1)
        now = time.time()
        window_start = int(now // _WINDOW_SECONDS) * _WINDOW_SECONDS
        rkey = f"rl:{scope}:{client_key}:{window_start}"
        n = r.incr(rkey)
        if n == 1:
            r.expire(rkey, _WINDOW_SECONDS + 5)
        return (n <= limit, n)
    except Exception:
        return None


def _memory_incr(scope: str, client_key: str, limit: int) -> tuple[bool, int]:
    """In-memory sliding window. Returns (allowed, current_count)."""
    with _memory_lock:
        now = time.time()
        bucket = _memory[scope]
        if client_key in bucket:
            count, start = bucket[client_key]
            if now - start >= _WINDOW_SECONDS:
                bucket[client_key] = (1, now)
                return (True, 1)
            bucket[client_key] = (count + 1, start)
            return (count + 1 <= limit, count + 1)
        bucket[client_key] = (1, now)
        return (True, 1)


def check_rate_limit(scope: str, client_key: str, limit: int, use_redis: bool = True) -> tuple[bool, int]:
    """
    Check and increment rate limit. Returns (allowed, current_count).
    If use_redis and Redis is available, use Redis; else in-memory.
    """
    if use_redis:
        out = _redis_incr(scope, client_key, limit)
        if out is not None:
            return out
    return _memory_incr(scope, client_key, limit)
