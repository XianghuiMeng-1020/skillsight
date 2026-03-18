import json
import logging
import os
import subprocess
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from qdrant_client.http import models as qm

try:
    from backend.app.db.deps import get_db
    from backend.app.deps import check_doc_access
    from backend.app.embeddings import embed_texts, emb_dim
    from backend.app.security import Identity, require_auth
    from backend.app.vector_store import get_client, ensure_collection, upsert_points, delete_by_doc_id, _qdrant_base_url
except ImportError:
    from app.db.deps import get_db
    from app.deps import check_doc_access
    from app.embeddings import embed_texts, emb_dim
    from app.security import Identity, require_auth
    from app.vector_store import get_client, ensure_collection, upsert_points, delete_by_doc_id, _qdrant_base_url

router = APIRouter(prefix="/chunks", tags=["chunks"])
_log = logging.getLogger(__name__)


def _qdrant_url(path: str) -> str:
    return _qdrant_base_url() + path


def _qdrant_curl_headers() -> list:
    """Return curl -H args for Qdrant Cloud API key when set."""
    api_key = os.getenv("QDRANT_API_KEY", "").strip()
    if api_key:
        return ["-H", f"api-key: {api_key}"]
    return []


def _ensure_collection_via_curl(dim: int) -> None:
    url = _qdrant_url("/collections/chunks_v1")
    headers = _qdrant_curl_headers()
    r = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}"] + headers + [url], capture_output=True, text=True, timeout=10)
    if r.returncode == 0 and r.stdout.strip() == "200":
        return
    body = json.dumps({"vectors": {"size": dim, "distance": "Cosine"}})
    r2 = subprocess.run(["curl", "-sS", "-X", "PUT", url] + headers + ["-H", "Content-Type: application/json", "-d", body],
                        capture_output=True, timeout=10)
    if r2.returncode != 0:
        raise RuntimeError(f"Failed to create Qdrant collection: {r2.stderr or r2.stdout}")


def _delete_by_doc_id_via_curl(doc_id: str) -> None:
    url = _qdrant_url("/collections/chunks_v1/points/delete")
    body = json.dumps({"filter": {"must": [{"key": "doc_id", "match": {"value": doc_id}}]}})
    headers = _qdrant_curl_headers()
    subprocess.run(["curl", "-sS", "-X", "POST", url] + headers + ["-H", "Content-Type: application/json", "-d", body],
                  capture_output=True, timeout=10)


def _upsert_via_curl(rows: list, vecs: list) -> None:
    """Fallback: upsert to Qdrant via curl when Python client returns 502."""
    url = _qdrant_url("/collections/chunks_v1/points")
    headers = _qdrant_curl_headers()
    BATCH = 20
    for i in range(0, len(rows), BATCH):
        batch_rows = rows[i:i + BATCH]
        batch_vecs = vecs[i:i + BATCH]
        points = []
        for r, v in zip(batch_rows, batch_vecs):
            points.append({
                "id": r["chunk_id"],
                "vector": v,
                "payload": {
                    "chunk_id": r["chunk_id"],
                    "doc_id": r["doc_id"],
                    "idx": int(r["idx"]),
                    "snippet": r["snippet"],
                    "section_path": r["section_path"],
                    "page_start": r["page_start"],
                    "page_end": r["page_end"],
                    "created_at": str(r["created_at"]),
                },
            })
        body = json.dumps({"points": points})
        result = subprocess.run(
            ["curl", "-sS", "-X", "PUT", url] + headers + ["-H", "Content-Type: application/json", "-d", "@-"],
            input=body,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"curl upsert failed: {result.stderr or result.stdout}")


@router.get("")
def list_chunks(
    doc_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    try:
        if doc_id:
            rows = db.execute(
                text("SELECT chunk_id, doc_id, snippet, created_at FROM chunks WHERE doc_id = :doc_id ORDER BY created_at DESC LIMIT :limit"),
                {"doc_id": doc_id, "limit": limit},
            ).mappings().all()
        else:
            rows = db.execute(
                text("SELECT chunk_id, doc_id, snippet, created_at FROM chunks ORDER BY created_at DESC LIMIT :limit"),
                {"limit": limit},
            ).mappings().all()
        return {"count": len(rows), "items": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/chunks failed: {type(e).__name__}: {e}")


@router.post("/embed/{doc_id}")
def embed_document_chunks(
    doc_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Generate embeddings for all chunks of a document synchronously.
    
    This is useful for demo/testing when Redis queue is not available.
    For production, use /jobs/enqueue/{doc_id} instead.
    """
    try:
        check_doc_access(ident, doc_id, db)
        # Fetch all chunks for this document
        rows = db.execute(
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
                WHERE doc_id = :doc_id
                ORDER BY idx ASC
            """),
            {"doc_id": doc_id},
        ).mappings().all()
        
        if not rows:
            raise HTTPException(status_code=404, detail="No chunks found for this document")

        texts = []
        for r in rows:
            ct = r.get("chunk_text")
            sn = (r.get("snippet") or "").strip()
            if ct is not None and str(ct).strip():
                texts.append(str(ct))
            elif sn:
                texts.append(sn)
            else:
                texts.append("(no extractable text)")
        vecs = embed_texts(texts)
        
        client = get_client()
        use_curl = False
        if client:
            try:
                ensure_collection(client, emb_dim())
                delete_by_doc_id(client, doc_id)
                points = [qm.PointStruct(id=r["chunk_id"], vector=v, payload={
                    "chunk_id": r["chunk_id"], "doc_id": r["doc_id"], "idx": int(r["idx"]),
                    "snippet": r["snippet"], "section_path": r["section_path"],
                    "page_start": r["page_start"], "page_end": r["page_end"],
                    "created_at": str(r["created_at"]),
                }) for r, v in zip(rows, vecs)]
                if points:
                    upsert_points(client, points)
            except Exception as exc:
                _log.warning("qdrant upsert failed, falling back to curl: %s", exc)
                use_curl = True
        else:
            use_curl = True
        
        if use_curl:
            _ensure_collection_via_curl(emb_dim())
            _delete_by_doc_id_via_curl(doc_id)
            _upsert_via_curl(rows, vecs)
        
        return {
            "doc_id": doc_id,
            "chunks_embedded": len(rows),
            "embedding_dim": emb_dim(),
            "message": "Embeddings generated and stored in Qdrant",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/chunks/embed/{doc_id} failed: {type(e).__name__}: {e}")


@router.get("/{chunk_id}")
def get_chunk(
    chunk_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """Get a specific chunk by ID."""
    try:
        row = db.execute(
            text("""
                SELECT 
                    chunk_id::text as chunk_id, 
                    doc_id::text as doc_id, 
                    idx, 
                    char_start,
                    char_end,
                    snippet, 
                    quote_hash,
                    section_path, 
                    page_start, 
                    page_end, 
                    created_at,
                    chunk_text
                FROM chunks
                WHERE chunk_id = :chunk_id
            """),
            {"chunk_id": chunk_id},
        ).mappings().first()
        
        if not row:
            raise HTTPException(status_code=404, detail="Chunk not found")
        
        return dict(row)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/chunks/{chunk_id} failed: {type(e).__name__}: {e}")
