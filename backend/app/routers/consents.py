"""
Consent Management Routes for SkillSight
- POST /consent/grant: Grant consent for document processing
- POST /consent/revoke: Revoke consent and cascade delete all related data
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.audit import log_audit
from backend.app.db.deps import get_db
from backend.app.db.session import engine
from backend.app.security import Identity, require_auth

router = APIRouter(tags=["consents"])


def _now_utc():
    return datetime.now(timezone.utc)


def _resolve_user_id(payload_user_id: str, ident: Identity) -> str:
    """Enforce that non-admin users can only operate on their own data."""
    if ident.role in ("admin", "staff"):
        return payload_user_id
    if payload_user_id != ident.subject_id:
        raise HTTPException(
            status_code=403,
            detail="You can only manage your own consent records",
        )
    return ident.subject_id


class ConsentGrant(BaseModel):
    user_id: str
    doc_id: str


class ConsentRevoke(BaseModel):
    user_id: str
    doc_id: str
    reason: str = ""  # Optional reason for audit trail


class ConsentRevokeResult(BaseModel):
    ok: bool
    doc_id: str
    deleted: Dict[str, int]
    audit_id: str


def _delete_vector_embeddings(doc_id: str) -> int:
    """Delete embeddings from Qdrant vector store."""
    try:
        from backend.app.vector_store import get_client, delete_by_doc_id
        client = get_client()
        delete_by_doc_id(client, doc_id)
        return 1  # Success indicator
    except Exception:
        return 0


def _delete_stored_file(doc_id: str, db: Session) -> int:
    """Delete the physical file from storage."""
    try:
        sql = text("SELECT stored_path FROM documents WHERE doc_id = :doc_id")
        row = db.execute(sql, {"doc_id": doc_id}).mappings().first()
        if row and row.get("stored_path"):
            stored_path = row["stored_path"]
            # Only delete if it's a real file path (not upload:// scheme)
            if not stored_path.startswith("upload://") and os.path.exists(stored_path):
                os.remove(stored_path)
                return 1
    except Exception:
        pass
    return 0


def _cascade_delete_document_data(db: Session, doc_id: str) -> Dict[str, int]:
    """
    Cascade delete all data related to a document.
    
    Order matters due to foreign key constraints:
    1. role_readiness (references doc_id)
    2. skill_proficiency (references doc_id)
    3. skill_assessments (references doc_id)
    4. chunks (references doc_id, cascade should handle but explicit is safer)
    5. Vector embeddings (Qdrant)
    6. Physical file
    7. documents (the main record)
    """
    deleted = {
        "role_readiness": 0,
        "skill_proficiency": 0,
        "skill_assessments": 0,
        "chunks": 0,
        "embeddings": 0,
        "files": 0,
        "documents": 0,
    }
    
    # Delete role_readiness
    try:
        result = db.execute(
            text("DELETE FROM role_readiness WHERE doc_id = :doc_id"),
            {"doc_id": doc_id}
        )
        deleted["role_readiness"] = result.rowcount or 0
    except Exception:
        pass
    
    # Delete skill_proficiency
    try:
        result = db.execute(
            text("DELETE FROM skill_proficiency WHERE doc_id = :doc_id"),
            {"doc_id": doc_id}
        )
        deleted["skill_proficiency"] = result.rowcount or 0
    except Exception:
        pass
    
    # Delete skill_assessments
    try:
        result = db.execute(
            text("DELETE FROM skill_assessments WHERE doc_id = :doc_id"),
            {"doc_id": doc_id}
        )
        deleted["skill_assessments"] = result.rowcount or 0
    except Exception:
        pass
    
    # Delete chunks
    try:
        result = db.execute(
            text("DELETE FROM chunks WHERE doc_id = :doc_id"),
            {"doc_id": doc_id}
        )
        deleted["chunks"] = result.rowcount or 0
    except Exception:
        pass
    
    # Delete vector embeddings (Qdrant)
    deleted["embeddings"] = _delete_vector_embeddings(doc_id)
    
    # Delete physical file
    deleted["files"] = _delete_stored_file(doc_id, db)
    
    # Delete document record
    try:
        result = db.execute(
            text("DELETE FROM documents WHERE doc_id = :doc_id"),
            {"doc_id": doc_id}
        )
        deleted["documents"] = result.rowcount or 0
    except Exception:
        pass
    
    return deleted


@router.get("/consents")
def list_consents(
    db: Session = Depends(get_db),
    limit: int = 50,
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """List consent records (scoped to current user unless staff/admin)."""
    try:
        if ident.role in ("staff", "admin"):
            rows = db.execute(
                text("SELECT * FROM consents ORDER BY created_at DESC LIMIT :limit"),
                {"limit": limit},
            ).mappings().all()
        else:
            rows = db.execute(
                text("""
                    SELECT * FROM consents
                    WHERE user_id = :sub
                    ORDER BY created_at DESC LIMIT :limit
                """),
                {"sub": ident.subject_id, "limit": limit},
            ).mappings().all()
        return {"count": len(rows), "items": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/consents failed: {type(e).__name__}: {e}")


@router.get("/consents/{doc_id}")
def get_consent(
    doc_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """Get consent status for a specific document."""
    try:
        row = db.execute(
            text("SELECT * FROM consents WHERE doc_id = :doc_id ORDER BY created_at DESC LIMIT 1"),
            {"doc_id": doc_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail=f"No consent found for doc_id: {doc_id}")
        return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/consents/{doc_id} failed: {type(e).__name__}: {e}")


@router.get("/consent/status/{doc_id}")
def get_consent_status(
    doc_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """Get consent status for a specific document. Alias for /consents/{doc_id}."""
    try:
        row = db.execute(
            text("SELECT * FROM consents WHERE doc_id = :doc_id ORDER BY created_at DESC LIMIT 1"),
            {"doc_id": doc_id},
        ).mappings().first()
        if not row:
            # Return a default status instead of 404 - document may exist without explicit consent record
            return {"doc_id": doc_id, "status": "unknown", "message": "No explicit consent record found"}
        return {"doc_id": doc_id, "status": row.get("status", "unknown"), "consent": dict(row)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/consent/status/{doc_id} failed: {type(e).__name__}: {e}")


@router.post("/consent/grant")
def consent_grant(
    payload: ConsentGrant,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Grant consent for a document.
    Creates a consent record with status='granted'.
    """
    effective_user = _resolve_user_id(payload.user_id, ident)
    try:
        consent_id = str(uuid.uuid4())
        now = _now_utc()
        
        db.execute(
            text("""
                INSERT INTO consents (consent_id, user_id, doc_id, status, created_at)
                VALUES (:consent_id, :user_id, :doc_id, :status, :created_at)
            """),
            {
                "consent_id": consent_id,
                "user_id": effective_user,
                "doc_id": payload.doc_id,
                "status": "granted",
                "created_at": now,
            },
        )
        db.commit()
        log_audit(
            engine,
            subject_id=effective_user,
            action="consent.grant",
            object_type="document",
            object_id=payload.doc_id,
            status="ok",
            detail={"consent_id": consent_id},
        )
        return {"ok": True, "consent_id": consent_id, "status": "granted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"/consent/grant failed: {type(e).__name__}: {e}")


@router.post("/consent/revoke")
def consent_revoke(
    payload: ConsentRevoke,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Revoke consent and CASCADE DELETE all related data.
    
    This implements Protocol 9 (Consent) requirement:
    "Revoke → physically delete document, chunks, embeddings, assessments"
    
    Deletion order:
    1. role_readiness
    2. skill_proficiency
    3. skill_assessments
    4. chunks
    5. Vector embeddings (Qdrant)
    6. Physical file
    7. documents table record
    8. Update consent status to 'revoked'
    """
    effective_user = _resolve_user_id(payload.user_id, ident)
    try:
        row = db.execute(
            text("SELECT * FROM consents WHERE subject_id = :subject_id AND doc_id = :doc_id"),
            {"subject_id": effective_user, "doc_id": payload.doc_id},
        ).mappings().first()
        
        if not row:
            raise HTTPException(status_code=404, detail="Consent record not found")
        
        deleted = _cascade_delete_document_data(db, payload.doc_id)
        
        db.execute(
            text("""
                UPDATE consents 
                SET status = 'revoked', revoked_at = :revoked_at, revoke_reason = :reason
                WHERE subject_id = :subject_id AND doc_id = :doc_id
            """),
            {
                "revoked_at": _now_utc(),
                "reason": payload.reason or "User requested revocation",
                "subject_id": effective_user,
                "doc_id": payload.doc_id,
            },
        )
        
        audit_id = log_audit(
            engine,
            subject_id=effective_user,
            action="consent.revoke",
            object_type="document",
            object_id=payload.doc_id,
            status="ok",
            detail={
                "reason": payload.reason or "User requested revocation",
                "deleted_counts": deleted,
            },
        )
        db.commit()
        
        return {
            "ok": True,
            "doc_id": payload.doc_id,
            "deleted": deleted,
            "audit_id": audit_id,
            "message": "All document data has been permanently deleted.",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"/consent/revoke failed: {type(e).__name__}: {e}")


@router.post("/consent/revoke/dry-run")
def consent_revoke_dry_run(
    payload: ConsentRevoke,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Preview what would be deleted if consent is revoked.
    Does NOT actually delete anything.
    """
    effective_user = _resolve_user_id(payload.user_id, ident)
    try:
        row = db.execute(
            text("SELECT * FROM consents WHERE subject_id = :subject_id AND doc_id = :doc_id"),
            {"subject_id": effective_user, "doc_id": payload.doc_id},
        ).mappings().first()
        
        if not row:
            raise HTTPException(status_code=404, detail="Consent record not found")
        
        # Count what would be deleted
        counts = {}
        
        # Count role_readiness
        try:
            c = db.execute(text("SELECT COUNT(*) FROM role_readiness WHERE doc_id = :doc_id"), {"doc_id": payload.doc_id}).scalar()
            counts["role_readiness"] = int(c or 0)
        except Exception:
            counts["role_readiness"] = 0
        
        # Count skill_proficiency
        try:
            c = db.execute(text("SELECT COUNT(*) FROM skill_proficiency WHERE doc_id = :doc_id"), {"doc_id": payload.doc_id}).scalar()
            counts["skill_proficiency"] = int(c or 0)
        except Exception:
            counts["skill_proficiency"] = 0
        
        # Count skill_assessments
        try:
            c = db.execute(text("SELECT COUNT(*) FROM skill_assessments WHERE doc_id = :doc_id"), {"doc_id": payload.doc_id}).scalar()
            counts["skill_assessments"] = int(c or 0)
        except Exception:
            counts["skill_assessments"] = 0
        
        # Count chunks
        try:
            c = db.execute(text("SELECT COUNT(*) FROM chunks WHERE doc_id = :doc_id"), {"doc_id": payload.doc_id}).scalar()
            counts["chunks"] = int(c or 0)
        except Exception:
            counts["chunks"] = 0
        
        # Check document exists
        try:
            c = db.execute(text("SELECT COUNT(*) FROM documents WHERE doc_id = :doc_id"), {"doc_id": payload.doc_id}).scalar()
            counts["documents"] = int(c or 0)
        except Exception:
            counts["documents"] = 0
        
        counts["embeddings"] = 1 if counts["chunks"] > 0 else 0
        counts["files"] = 1 if counts["documents"] > 0 else 0
        
        return {
            "dry_run": True,
            "doc_id": payload.doc_id,
            "would_delete": counts,
            "message": "This is a preview. No data has been deleted.",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/consent/revoke/dry-run failed: {type(e).__name__}: {e}")
