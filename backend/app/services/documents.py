from __future__ import annotations
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

# NOTE:
# This service is intentionally minimal for MVP smoke-check.
# It reads from existing DB tables (documents, chunks) if present.

def list_documents(db: Session, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    q = text("""
        SELECT doc_id, source, title, status, created_at
        FROM documents
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    rows = db.execute(q, {"limit": int(limit), "offset": int(offset)}).mappings().all()
    return [dict(r) for r in rows]

def get_document(db: Session, doc_id: str) -> Optional[Dict[str, Any]]:
    q = text("""
        SELECT doc_id, source, title, status, created_at
        FROM documents
        WHERE doc_id = :doc_id
        LIMIT 1
    """)
    row = db.execute(q, {"doc_id": doc_id}).mappings().first()
    return dict(row) if row else None

def list_chunks(db: Session, doc_id: str, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
    q = text("""
        SELECT chunk_id, doc_id, page_start, page_end, char_start, char_end, snippet, quote_hash, created_at
        FROM chunks
        WHERE doc_id = :doc_id
        ORDER BY created_at ASC
        LIMIT :limit OFFSET :offset
    """)
    rows = db.execute(q, {"doc_id": doc_id, "limit": int(limit), "offset": int(offset)}).mappings().all()
    return [dict(r) for r in rows]
