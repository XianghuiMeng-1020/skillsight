"""
FastAPI middleware: write one audit row per request for audited routes.
Uses unified audit schema; audit failures are logged with request_id and do not affect the response.
"""
from __future__ import annotations

import logging
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.app.audit import (
    _object_from_path,
    _path_should_audit,
    action_name_from_scope,
    log_audit,
)
from backend.app.db.session import engine
from backend.app.security import parse_token_optional

logger = logging.getLogger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id  # type: ignore[attr-defined]

        response = await call_next(request)

        path = request.scope.get("path") or request.url.path
        if not _path_should_audit(path):
            return response

        status_code = response.status_code
        status_str = str(status_code)
        error = None
        if status_code >= 500:
            error = "server_error"

        auth = request.headers.get("Authorization")
        payload = parse_token_optional(auth)
        subject_id = str(payload.get("sub", "anonymous")) if payload else "anonymous"

        action = action_name_from_scope("", path)
        object_type, object_id = _object_from_path(path, request.method)

        try:
            log_audit(
                engine,
                request_id=request_id,
                subject_id=subject_id,
                action=action,
                object_type=object_type,
                object_id=object_id,
                status=status_str,
                error=error,
                detail={"path": path, "method": request.method},
            )
        except Exception as e:  # pragma: no cover
            logger.error("audit middleware failed request_id=%s: %s", request_id, e, exc_info=True)

        return response
