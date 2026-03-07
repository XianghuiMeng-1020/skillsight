"""Shared dependencies for SkillSight."""
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.db.deps import get_db
from backend.app.security import Identity, require_auth

_log = logging.getLogger(__name__)


def check_doc_access(ident: Identity, doc_id: str, db: Session) -> None:
    """Verify user has access to document. Raises 403/404 if not."""
    # staff/admin can access all
    if ident.role in ("staff", "admin"):
        return
    # Check consents - user owns doc if they have granted consent (user_id or subject_id if column exists)
    try:
        row = db.execute(
            text("""
                SELECT 1 FROM consents
                WHERE doc_id = :doc_id AND status = 'granted'
                AND user_id = :sub
                LIMIT 1
            """),
            {"doc_id": doc_id, "sub": ident.subject_id},
        ).first()
    except Exception as exc:
        _log.warning("consent access check failed: %s", exc)
        row = None
    if not row:
        from fastapi import HTTPException
        # Check if doc exists
        doc = db.execute(text("SELECT 1 FROM documents WHERE doc_id = :doc_id"), {"doc_id": doc_id}).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        raise HTTPException(status_code=403, detail="Access denied to this document")
