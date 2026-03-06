"""
Background Worker for SkillSight
Processes document parsing and embedding jobs.
"""
import os
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

from rq import Worker
from redis import Redis
from sqlalchemy import text

# Import from backend.app for consistent PYTHONPATH (e.g. Docker /opt/src)
try:
    from backend.app.db.session import engine
    from backend.app.parsers import parse_file_to_chunks
    from backend.app.vector_store import get_client, ensure_collection, upsert_points, delete_by_doc_id
    from backend.app.embeddings import embed_texts, emb_dim
    from backend.app.queue import enqueue_assessment_repair
except ImportError:
    from app.db.session import engine
    from app.parsers import parse_file_to_chunks
    from app.vector_store import get_client, ensure_collection, upsert_points, delete_by_doc_id
    from app.embeddings import embed_texts, emb_dim
    from app.queue import enqueue_assessment_repair
from qdrant_client.http import models as qm

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
QUEUE_NAME = "skillsight"
REPAIR_BACKOFF_BASE_SECONDS = max(1, int(os.getenv("ASSESSMENT_REPAIR_BACKOFF_BASE_SECONDS", "5")))
REPAIR_BACKOFF_MAX_SECONDS = max(1, int(os.getenv("ASSESSMENT_REPAIR_BACKOFF_MAX_SECONDS", "300")))


def _repair_backoff_seconds(next_attempt: int) -> int:
    # Exponential backoff: base * 2^(attempt-1), clamped by max.
    raw = REPAIR_BACKOFF_BASE_SECONDS * (2 ** max(0, next_attempt - 1))
    return min(raw, REPAIR_BACKOFF_MAX_SECONDS)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _make_snippet(text: str, n: int = 220) -> str:
    t = (text or "").strip().replace("\n", " ")
    return t[:n] + ("..." if len(t) > n else "")


def _hash_quote(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def ensure_chunks_table():
    """Create chunks table if it doesn't exist."""
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS chunks (
          chunk_id UUID PRIMARY KEY,
          doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
          idx INTEGER NOT NULL,
          char_start INTEGER NOT NULL,
          char_end INTEGER NOT NULL,
          snippet TEXT NOT NULL,
          quote_hash TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL,
          chunk_text TEXT NOT NULL,
          section_path TEXT,
          page_start INTEGER,
          page_end INTEGER
        );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);"))


def update_job(job_id: str, status: str, attempts: int, last_error: str | None = None):
    """Update job status in database."""
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE jobs
                SET status=:status, attempts=:attempts, last_error=:last_error, updated_at=now()
                WHERE job_id = (:job_id)::uuid
            """),
            {"job_id": job_id, "status": status, "attempts": attempts, "last_error": last_error},
        )


def process_doc(doc_id: str, job_id: str):
    """
    Process a document:
    1. Fetch document metadata
    2. Parse file into chunks
    3. Store chunks in database
    4. Generate embeddings and store in Qdrant
    """
    # Fetch document metadata
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT stored_path, filename FROM documents WHERE doc_id = (:doc_id)::uuid"),
            {"doc_id": doc_id},
        ).mappings().first()
    
    if not row:
        raise RuntimeError("Document not found")
    
    stored_path = row["stored_path"]
    filename = row["filename"]
    
    # Handle virtual paths (upload://, memory://) – chunks already in DB, only regenerate embeddings
    if stored_path.startswith("upload://") or stored_path.startswith("memory://"):
        pass
    elif not os.path.exists(stored_path):
        raise RuntimeError(f"File not found: {stored_path}")
    else:
        # Parse file into chunks
        chunk_dicts = parse_file_to_chunks(file_path=stored_path)
        
        # Ensure chunks table exists
        ensure_chunks_table()
        
        # Replace chunks in DB for doc
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM chunks WHERE doc_id = (:doc_id)::uuid"), {"doc_id": doc_id})
            
            for idx, ch in enumerate(chunk_dicts):
                ct = (ch.get("chunk_text") or "").strip()
                if not ct:
                    continue
                
                chunk_id = str(uuid.uuid4())
                snippet = ch.get("snippet") or _make_snippet(ct)
                quote_hash = ch.get("quote_hash") or _hash_quote(ct)
                
                conn.execute(
                    text("""
                        INSERT INTO chunks (
                            chunk_id, doc_id, idx, char_start, char_end, 
                            chunk_text, snippet, quote_hash, created_at, 
                            section_path, page_start, page_end
                        )
                        VALUES (
                            (:chunk_id)::uuid, (:doc_id)::uuid, :idx, :char_start, :char_end,
                            :chunk_text, :snippet, :quote_hash, now(),
                            :section_path, :page_start, :page_end
                        )
                    """),
                    {
                        "chunk_id": chunk_id,
                        "doc_id": doc_id,
                        "idx": idx,
                        "char_start": int(ch.get("char_start") or 0),
                        "char_end": int(ch.get("char_end") or 0),
                        "chunk_text": ct,
                        "snippet": snippet,
                        "quote_hash": quote_hash,
                        "section_path": ch.get("section_path"),
                        "page_start": ch.get("page_start"),
                        "page_end": ch.get("page_end"),
                    },
                )
    
    # Re-index embeddings for this doc_id
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT 
                    chunk_id::text as chunk_id, 
                    doc_id::text as doc_id, 
                    idx, 
                    snippet, 
                    section_path, 
                    page_start, 
                    page_end, 
                    created_at, 
                    chunk_text
                FROM chunks
                WHERE doc_id = (:doc_id)::uuid
                ORDER BY idx ASC
            """),
            {"doc_id": doc_id},
        ).mappings().all()
    
    if not rows:
        return

    texts = [r["chunk_text"] for r in rows]
    vecs = embed_texts(texts)
    
    points = []
    for r, v in zip(rows, vecs):
        payload = {
            "chunk_id": r["chunk_id"],
            "doc_id": r["doc_id"],
            "idx": int(r["idx"]),
            "snippet": r["snippet"],
            "section_path": r["section_path"],
            "page_start": r["page_start"],
            "page_end": r["page_end"],
            "created_at": str(r["created_at"]),
        }
        points.append(qm.PointStruct(id=r["chunk_id"], vector=v, payload=payload))
    
    if points:
        client = get_client()
        ensure_collection(client, emb_dim())
        try:
            delete_by_doc_id(client, doc_id)
            upsert_points(client, points)
        except Exception as qdrant_err:
            # Compensate: mark job for re-index so chunks aren't orphaned
            try:
                with engine.begin() as conn:
                    conn.execute(text("""
                        UPDATE jobs SET status = 'qdrant_failed', last_error = :err, updated_at = now()
                        WHERE doc_id = (:doc_id)::uuid AND status = 'running'
                    """), {"doc_id": doc_id, "err": str(qdrant_err)[:500]})
            except Exception:
                pass
            raise


def run_job(doc_id: str, job_id: str):
    """Run a document processing job."""
    # Get current attempts
    with engine.connect() as conn:
        r = conn.execute(
            text("SELECT attempts FROM jobs WHERE job_id = (:job_id)::uuid"),
            {"job_id": job_id}
        ).first()
        attempts = int(r[0]) if r else 0
    
    attempts += 1
    update_job(job_id, "running", attempts, None)
    
    try:
        process_doc(doc_id, job_id)
        update_job(job_id, "succeeded", attempts, None)
    except Exception as e:
        update_job(job_id, "failed", attempts, f"{type(e).__name__}: {e}")
        raise


def run_assessment_repair(session_id: str, repair_job_id: str):
    """
    Run async repair for interactive assessment skill sync.
    """
    try:
        from backend.app.routers.interactive_assess import _persist_skill_outcome
    except ImportError:
        from app.routers.interactive_assess import _persist_skill_outcome

    attempts = 0
    max_attempts = 1
    try:
        with engine.begin() as conn:
            row = conn.execute(text("""
                SELECT * FROM assessment_repair_jobs
                WHERE repair_job_id = (:repair_job_id)::uuid
                LIMIT 1
            """), {"repair_job_id": repair_job_id}).mappings().first()
            if not row:
                raise RuntimeError("repair job not found")

            state = conn.execute(text("""
                UPDATE assessment_repair_jobs
                SET status = 'running', attempts = attempts + 1, updated_at = now()
                WHERE repair_job_id = (:repair_job_id)::uuid
                RETURNING attempts, max_attempts
            """), {"repair_job_id": repair_job_id}).mappings().first()
            if state:
                attempts = int(state.get("attempts") or 0)
                max_attempts = int(state.get("max_attempts") or 1)
            else:
                attempts = int(row.get("attempts") or 0) + 1
                max_attempts = int(row.get("max_attempts") or 1)

        raw_attempt_id = row.get("attempt_id")
        if raw_attempt_id is None:
            raise RuntimeError("repair job has no attempt_id")
        with engine.connect() as conn:
            attempt = conn.execute(text("""
                SELECT * FROM assessment_attempts
                WHERE attempt_id = (:attempt_id)::uuid
                LIMIT 1
            """), {"attempt_id": str(raw_attempt_id)}).mappings().first()
        if not attempt:
            raise RuntimeError("attempt not found for repair job")

        response_data = attempt.get("response_data") or {}
        if isinstance(response_data, str):
            import json
            try:
                response_data = json.loads(response_data)
            except Exception:
                response_data = {}
        if not isinstance(response_data, dict):
            response_data = {}

        evaluation = attempt.get("evaluation") or {}
        if isinstance(evaluation, str):
            import json
            try:
                evaluation = json.loads(evaluation)
            except Exception:
                evaluation = {}
        if not isinstance(evaluation, dict):
            evaluation = {}

        assessment_type = str(row.get("assessment_type") or "")
        if assessment_type == "communication":
            response_text = str(response_data.get("transcript") or "")
        elif assessment_type == "programming":
            response_text = str(response_data.get("code") or "")
        elif assessment_type == "writing":
            response_text = str(response_data.get("content") or "")
        else:
            response_text = str(row.get("response_text") or "")

        # Use a short-lived ORM session to reuse router persistence code.
        try:
            from backend.app.db.session import SessionLocal
        except ImportError:
            from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            _persist_skill_outcome(
                db,
                user_id=str(row["user_id"]),
                skill_id=str(row.get("skill_id") or ""),
                assessment_type=assessment_type,
                response_text=response_text,
                evaluation=evaluation,
                session_id=session_id,
                attempt_id=str(row["attempt_id"]),
            )
            db.commit()
        finally:
            db.close()

        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE assessment_repair_jobs
                SET status = 'succeeded', last_error = NULL, next_retry_at = NULL, dead_lettered_at = NULL, dead_letter_reason = NULL, updated_at = now()
                WHERE repair_job_id = (:repair_job_id)::uuid
            """), {"repair_job_id": repair_job_id})
    except Exception as e:
        err_text = f"{type(e).__name__}: {e}"
        if attempts < max_attempts:
            next_attempt = attempts + 1
            delay_seconds = _repair_backoff_seconds(next_attempt)
            next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
            rq_job_id = enqueue_assessment_repair(session_id=session_id, repair_job_id=repair_job_id, delay_seconds=delay_seconds)
            with engine.begin() as conn:
                conn.execute(text("""
                    UPDATE assessment_repair_jobs
                    SET status = 'pending',
                        last_error = :last_error,
                        next_retry_at = :next_retry_at,
                        rq_job_id = :rq_job_id,
                        updated_at = now()
                    WHERE repair_job_id = (:repair_job_id)::uuid
                """), {
                    "repair_job_id": repair_job_id,
                    "last_error": err_text,
                    "next_retry_at": next_retry_at,
                    "rq_job_id": rq_job_id,
                })
            raise
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE assessment_repair_jobs
                SET status = 'dead_letter',
                    last_error = :last_error,
                    dead_lettered_at = now(),
                    dead_letter_reason = :dead_letter_reason,
                    next_retry_at = NULL,
                    updated_at = now()
                WHERE repair_job_id = (:repair_job_id)::uuid
            """), {
                "repair_job_id": repair_job_id,
                "last_error": err_text,
                "dead_letter_reason": "max_attempts_exhausted",
            })
        raise


if __name__ == "__main__":
    redis_conn = Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
    w = Worker([QUEUE_NAME], connection=redis_conn)
    print(f"Starting SkillSight worker on queue '{QUEUE_NAME}'...")
    w.work()
