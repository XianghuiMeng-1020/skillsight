import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from backend.app.db.deps import get_db
    from backend.app.queue import enqueue_process_doc, get_queue_status
    from backend.app.security import Identity, require_auth
except ImportError:
    from app.db.deps import get_db
    from app.queue import enqueue_process_doc, get_queue_status
    from app.security import Identity, require_auth

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _now_utc():
    return datetime.now(timezone.utc)


@router.get("")
def list_jobs(db: Session = Depends(get_db), limit: int = 50, ident: Identity = Depends(require_auth)):
    if ident.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can list all jobs")
    try:
        rows = db.execute(
            text("SELECT * FROM jobs ORDER BY created_at DESC LIMIT :limit"),
            {"limit": limit},
        ).mappings().all()
        return {"count": len(rows), "items": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/jobs failed: {type(e).__name__}: {e}")


@router.get("/queue/status")
def queue_status(ident: Identity = Depends(require_auth)):
    """Get Redis queue status."""
    return get_queue_status()


@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db), ident: Identity = Depends(require_auth)):
    try:
        row = db.execute(
            text("SELECT * FROM jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="job not found")
        return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/jobs/{job_id} failed: {type(e).__name__}: {e}")


@router.post("/{job_id}/retry")
def retry_job(job_id: str, db: Session = Depends(get_db), ident: Identity = Depends(require_auth)):
    """
    Retry a failed job by resetting its status to 'pending' and enqueuing it.
    Only admin can retry jobs.
    """
    if ident.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can retry jobs")
    try:
        # Get job details
        row = db.execute(
            text("SELECT * FROM jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).mappings().first()
        
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        
        doc_id = str(row["doc_id"])
        
        # Reset job status
        db.execute(
            text("""
                UPDATE jobs 
                SET status = 'pending', last_error = NULL, updated_at = :now
                WHERE job_id = :job_id
            """),
            {"job_id": job_id, "now": _now_utc()},
        )
        db.commit()
        
        # Enqueue for processing
        rq_job_id = enqueue_process_doc(doc_id, job_id)
        
        return {
            "job_id": job_id,
            "doc_id": doc_id,
            "status": "pending",
            "rq_job_id": rq_job_id,
            "message": "Job reset and enqueued for retry" if rq_job_id else "Job reset but queue unavailable",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"/jobs/{job_id}/retry failed: {type(e).__name__}: {e}")


@router.post("/enqueue/{doc_id}")
def enqueue_doc_job(doc_id: str, db: Session = Depends(get_db), ident: Identity = Depends(require_auth)):
    """
    Create and enqueue a new job for a document.
    Useful for manually triggering embedding generation.
    Only admin can enqueue jobs.
    """
    if ident.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can enqueue jobs")
    try:
        # Verify document exists
        doc = db.execute(
            text("SELECT doc_id FROM documents WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        ).first()
        
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Create new job
        job_id = str(uuid.uuid4())
        now = _now_utc()
        
        db.execute(
            text("""
                INSERT INTO jobs (job_id, doc_id, status, attempts, created_at)
                VALUES (:job_id, :doc_id, 'pending', 0, :now)
            """),
            {"job_id": job_id, "doc_id": doc_id, "now": now},
        )
        db.commit()
        
        # Enqueue for processing
        rq_job_id = enqueue_process_doc(doc_id, job_id)
        
        return {
            "job_id": job_id,
            "doc_id": doc_id,
            "status": "pending",
            "rq_job_id": rq_job_id,
            "message": "Job created and enqueued" if rq_job_id else "Job created but queue unavailable",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"/jobs/enqueue/{doc_id} failed: {type(e).__name__}: {e}")
