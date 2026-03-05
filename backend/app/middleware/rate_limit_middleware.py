"""
Rate limiting middleware: /auth/*, /documents/upload*, /ai/*, /search/*.
Redis-backed when available; in-memory for dev. ENV: RATE_LIMIT_ENABLED, RATE_LIMIT_PER_MINUTE_*.
"""
from __future__ import annotations

from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.app.rate_limit import (
    _client_key,
    _is_enabled,
    _limit_for_scope,
    _scope_for_path,
    check_rate_limit,
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not _is_enabled():
            return await call_next(request)

        path = request.scope.get("path") or request.url.path
        scope = _scope_for_path(path)
        if scope is None:
            return await call_next(request)

        limit = _limit_for_scope(scope)
        client_key = _client_key(request.scope)
        allowed, current = check_rate_limit(scope, client_key, limit)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "rate_limit_exceeded", "retry_after": 60},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)
