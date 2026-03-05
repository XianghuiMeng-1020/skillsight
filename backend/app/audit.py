"""
Unified audit logging for SkillSight (Protocol 8).
Single schema: audit_id, request_id, subject_id, action, object_type, object_id, status, error, detail, created_at.
Do not create DDL here; use alembic migrations only.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# Routes that must be audited (middleware writes one row per request for these)
# /bff/ first: ensure 100% BFF coverage (fail-open for any /bff/* path)
AUDITED_PATH_PREFIXES = (
    "/bff/",
    "/auth/dev_login",
    "/documents/upload",
    "/documents/import",
    "/documents/reindex",
    "/search/evidence_vector",
    "/ai/demonstration",
    "/ai/proficiency",
    "/assess/role_readiness",
    "/actions/recommend",
    "/consent/grant",
    "/consent/revoke",
    # BFF tier – student
    "/bff/student/auth/dev_login",
    "/bff/student/documents/upload",
    "/bff/student/chunks/embed",
    "/bff/student/search/evidence_vector",
    "/bff/student/profile",
    "/bff/student/roles/alignment",
    "/bff/student/actions/recommend",
    "/bff/student/consents",
    "/bff/student/consents/withdraw",
    "/bff/student/documents",
    "/bff/student/export",
    # BFF tier – staff (P3)
    "/bff/staff/auth/dev_login",
    "/bff/staff/courses",
    "/bff/staff/review",
    "/bff/staff/skills",
    "/bff/staff/audit",
    "/bff/staff/health",
    # BFF tier – programme (P3)
    "/bff/programme/auth/dev_login",
    "/bff/programme/programmes",
    "/bff/programme/audit",
    "/bff/programme/health",
    # BFF tier – admin (P3)
    "/bff/admin/auth/dev_login",
    "/bff/admin/onboarding",
    "/bff/admin/users",
    "/bff/admin/skills",
    "/bff/admin/roles",
    "/bff/admin/audit",
    "/bff/admin/metrics",
    "/bff/admin/health",
)


def log_audit(
    engine: Engine,
    *,
    request_id: Optional[str] = None,
    subject_id: str,
    action: str,
    object_type: str = "",
    object_id: Optional[str] = None,
    status: str = "",
    error: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Write one audit row. Uses canonical schema from migrations only.
    On failure logs error with request_id and does not raise (audit must not break requests).
    Returns the audit_id (UUID string).
    """
    audit_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    detail_json = json.dumps(detail or {}, default=str)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO audit_logs
                    (audit_id, request_id, subject_id, action, object_type, object_id, status, error, detail, created_at)
                    VALUES
                    ((:audit_id)::uuid, :request_id, :subject_id, :action, :object_type, :object_id,
                     :status, :error, (:detail)::jsonb, :created_at)
                """),
                {
                    "audit_id": audit_id,
                    "request_id": request_id,
                    "subject_id": subject_id,
                    "action": action,
                    "object_type": object_type or "",
                    "object_id": object_id,
                    "status": status,
                    "error": error,
                    "detail": detail_json,
                    "created_at": now,
                },
            )
    except Exception as e:  # pragma: no cover
        logger.error("audit write failed request_id=%s: %s", request_id, e, exc_info=True)
    return audit_id


def _path_should_audit(path: str) -> bool:
    """True if this path is in the audited set (by prefix)."""
    for p in AUDITED_PATH_PREFIXES:
        if path == p or path.startswith(p + "/") or (p.endswith("*") and path.startswith(p.rstrip("*"))):
            return True
    # Also match /documents/{id}/reindex
    if path.startswith("/documents/") and "/reindex" in path:
        return True
    return False


def _object_from_path(path: str, method: str) -> tuple[str, Optional[str]]:
    """Infer object_type and object_id from path when possible."""
    # /documents/import, /documents/upload, /documents/{doc_id}, /documents/{doc_id}/reindex
    if path.startswith("/documents/"):
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[1] not in ("import", "upload", "upload_multimodal"):
            return "document", parts[1]
        return "document", None
    if path.startswith("/search/"):
        return "search", None
    if path.startswith("/ai/"):
        return "ai", None
    if path.startswith("/assess/"):
        return "assess", None
    if path.startswith("/actions/"):
        return "action", None
    if path.startswith("/consent/"):
        return "consent", None
    if path.startswith("/auth/"):
        return "auth", None
    return "", None


def action_name_from_scope(scope: str, path: str) -> str:
    """Route name for audit action (e.g. auth.dev_login, documents.import)."""
    if path.startswith("/auth/"):
        return path.replace("/auth/", "auth.").strip("/") or "auth"
    if path.startswith("/documents/"):
        if "/import" in path:
            return "documents.import"
        if "/upload" in path:
            return "documents.upload"
        if "/reindex" in path:
            return "documents.reindex"
        return "documents"
    if path.startswith("/search/"):
        return "search.evidence_vector" if "evidence_vector" in path else "search"
    if path.startswith("/ai/"):
        return path.replace("/ai/", "ai.").strip("/") or "ai"
    if path.startswith("/assess/"):
        return "assess.role_readiness" if "role_readiness" in path else "assess"
    if path.startswith("/actions/"):
        return "actions.recommend" if "recommend" in path else "actions"
    if path.startswith("/consent/"):
        if "grant" in path:
            return "consent.grant"
        if "revoke" in path:
            return "consent.revoke"
        return "consent"
    if path.startswith("/bff/"):
        parts = path.strip("/").split("/")
        if len(parts) >= 3:
            return ".".join(parts[:3])  # e.g. bff.staff.courses
        return path.strip("/").replace("/", ".") or "bff"
    return scope or path.strip("/") or "unknown"
