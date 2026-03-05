import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from backend.app.db.deps import get_db
from backend.app.db.session import engine
from backend.app.deps import check_doc_access
from backend.app.security import Identity, require_auth

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))  # 50 MB

_MAGIC_SIGNATURES: Dict[str, list] = {
    ".pdf":  [b"%PDF"],
    ".docx": [b"PK\x03\x04"],
    ".pptx": [b"PK\x03\x04"],
    ".zip":  [b"PK\x03\x04"],
    ".png":  [b"\x89PNG"],
    ".jpg":  [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".gif":  [b"GIF87a", b"GIF89a"],
    ".webp": [b"RIFF"],
}


def _validate_magic(raw_bytes: bytes, ext: str) -> None:
    """Verify file magic bytes match extension. Skip for text-like formats."""
    sigs = _MAGIC_SIGNATURES.get(ext)
    if not sigs:
        return
    for sig in sigs:
        if raw_bytes[:len(sig)] == sig:
            return
    raise HTTPException(
        status_code=400,
        detail=f"File content does not match extension {ext}",
    )


# -----------------------------
# helpers
# -----------------------------
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_json(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, (str, bytes, bytearray)):
        try:
            return json.loads(v)
        except Exception:
            return v
    try:
        return json.loads(str(v))
    except Exception:
        return v


def _table_cols(table: str) -> List[str]:
    insp = inspect(engine)
    return [c["name"] for c in insp.get_columns(table, schema="public")]


def _chunk_text(s: str, chunk_size: int = 800, overlap: int = 100) -> List[Tuple[int, int, str]]:
    """
    Returns list of (char_start, char_end, chunk_text).
    """
    if s is None:
        return []
    s = s.strip("\ufeff")
    if s.strip() == "":
        return []

    n = len(s)
    out: List[Tuple[int, int, str]] = []
    i = 0
    step = max(1, chunk_size - overlap)

    while i < n:
        j = min(n, i + chunk_size)
        chunk = s[i:j]
        if chunk.strip() != "":
            out.append((i, j, chunk))
        if j >= n:
            break
        i += step

    return out


def _safe_snippet(s: str, max_len: int = 300) -> str:
    if s is None:
        return ""
    t = s.replace("\r\n", "\n").replace("\r", "\n").strip()
    t = " ".join(t.split())
    return t[:max_len]


def _sha256_text(s: str) -> str:
    if s is None:
        s = ""
    h = hashlib.sha256()
    h.update(s.encode("utf-8", errors="ignore"))
    return h.hexdigest()


def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b or b"")
    return h.hexdigest()


def _insert_one(db: Session, table: str, data: Dict[str, Any]) -> None:
    """
    Insert using ONLY columns that exist in current DB schema.
    """
    cols = set(_table_cols(table))
    use = {k: v for k, v in data.items() if k in cols}

    if not use:
        raise RuntimeError(f"no usable columns to insert into {table}")

    keys = list(use.keys())
    placeholders = [f":{k}" for k in keys]
    sql = text(f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({', '.join(placeholders)})")
    db.execute(sql, use)


# -----------------------------
# GET endpoints
# -----------------------------
@router.get("")
def list_documents(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Return {count, items}.
    """
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names(schema="public"))
        if "documents" not in tables:
            raise RuntimeError(f"'documents' table not found. public tables={sorted(tables)[:50]}")

        cols = [c["name"] for c in insp.get_columns("documents", schema="public")]

        want: List[str] = []
        for c in ["doc_id", "filename", "stored_path", "doc_type", "created_at"]:
            if c in cols and c not in want:
                want.append(c)

        # optional cols if present
        for c in ["title", "source_type", "storage_uri", "updated_at", "metadata_json"]:
            if c in cols and c not in want:
                want.append(c)

        if not want:
            want = cols[: min(len(cols), 12)]

        # Scope by subject: only docs user has consent for (staff/admin see all)
        if ident.role in ("staff", "admin"):
            total = db.execute(text("SELECT COUNT(*) FROM documents")).scalar() or 0
        else:
            total = db.execute(
                text("""
                    SELECT COUNT(*) FROM documents d
                    WHERE d.doc_id IN (
                        SELECT doc_id FROM consents
                        WHERE (subject_id = :sub OR user_id = :sub) AND status = 'granted'
                    )
                """),
                {"sub": ident.subject_id},
            ).scalar() or 0

        order = ""
        if "created_at" in cols:
            order = " ORDER BY created_at DESC NULLS LAST"
        elif "doc_id" in cols:
            order = " ORDER BY doc_id DESC"

        if ident.role in ("staff", "admin"):
            sql = text(f"SELECT {', '.join(want)} FROM documents{order} LIMIT :limit OFFSET :offset")
            rows = db.execute(sql, {"limit": limit, "offset": offset}).mappings().all()
        else:
            sql = text(f"""
                SELECT {', '.join(want)} FROM documents d
                WHERE d.doc_id IN (
                    SELECT doc_id FROM consents
                    WHERE (subject_id = :sub OR user_id = :sub) AND status = 'granted'
                ){order} LIMIT :limit OFFSET :offset
            """)
            rows = db.execute(sql, {"sub": ident.subject_id, "limit": limit, "offset": offset}).mappings().all()

        items: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            if "metadata_json" in d:
                d["metadata"] = _coerce_json(d.get("metadata_json"))
            if d.get("doc_id") is None and "id" in d and d.get("id") is not None:
                d["doc_id"] = d["id"]
            items.append(d)

        return {"count": int(total), "items": items}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/documents failed: {type(e).__name__}: {e}")


@router.get("/{doc_id}")
def get_document(
    doc_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        insp = inspect(engine)
        cols = [c["name"] for c in insp.get_columns("documents", schema="public")]

        want: List[str] = []
        for c in ["doc_id", "filename", "stored_path", "doc_type", "created_at"]:
            if c in cols and c not in want:
                want.append(c)
        for c in ["title", "source_type", "storage_uri", "updated_at", "metadata_json"]:
            if c in cols and c not in want:
                want.append(c)

        if not want:
            want = cols[: min(len(cols), 12)]

        check_doc_access(ident, doc_id, db)
        sql = text(f"SELECT {', '.join(want)} FROM documents WHERE doc_id = :doc_id LIMIT 1")
        row = db.execute(sql, {"doc_id": doc_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="document not found")

        d = dict(row)
        if "metadata_json" in d:
            d["metadata"] = _coerce_json(d.get("metadata_json"))
        return d

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/documents/{doc_id} failed: {type(e).__name__}: {e}")


@router.get("/{doc_id}/chunks")
def list_chunks_for_document(
    doc_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100000),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Return {count, items} for chunks of a doc.
    """
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names(schema="public"))
        if "chunks" not in tables:
            raise RuntimeError("'chunks' table not found")

        cols = [c["name"] for c in insp.get_columns("chunks", schema="public")]

        want: List[str] = []
        for c in [
            "chunk_id",
            "doc_id",
            "idx",
            "char_start",
            "char_end",
            "snippet",
            "quote_hash",
            "created_at",
            "chunk_text",
        ]:
            if c in cols and c not in want:
                want.append(c)

        # optional cols
        for c in ["page_start", "page_end", "storage_uri", "stored_path"]:
            if c in cols and c not in want:
                want.append(c)

        if not want:
            want = cols[: min(len(cols), 12)]

        total = db.execute(
            text("SELECT COUNT(*) FROM chunks WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        ).scalar() or 0

        order = ""
        if "idx" in cols:
            order = " ORDER BY idx ASC"
        elif "chunk_id" in cols:
            order = " ORDER BY chunk_id ASC"
        elif "created_at" in cols:
            order = " ORDER BY created_at ASC"

        sql = text(
            f"SELECT {', '.join(want)} FROM chunks WHERE doc_id = :doc_id{order} LIMIT :limit OFFSET :offset"
        )
        rows = db.execute(
            sql,
            {"doc_id": doc_id, "limit": limit, "offset": offset},
        ).mappings().all()

        items = [dict(r) for r in rows]
        return {"count": int(total), "items": items}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/documents/{doc_id}/chunks failed: {type(e).__name__}: {e}")


# -----------------------------
# POST /documents/import (txt only)
# -----------------------------
@router.post("/import")
async def import_document_txt(
    file: UploadFile = File(...),
    chunk_size: int = Query(default=800, ge=200, le=5000),
    overlap: int = Query(default=100, ge=0, le=2000),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Minimal ingestion loop (txt only), aligned to current DB NOT NULL constraints.

    documents (NOT NULL): doc_id, filename, stored_path, created_at, doc_type
    chunks (NOT NULL): chunk_id, doc_id, idx, char_start, char_end, snippet, quote_hash, created_at, chunk_text
    """
    try:
        filename = (file.filename or "uploaded.txt").strip()
        ext = os.path.splitext(filename)[1].lower()
        if ext != ".txt":
            raise HTTPException(status_code=400, detail="only .txt is supported in MVP import")

        raw_bytes = await file.read()
        if len(raw_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)} MB)")
        try:
            content = raw_bytes.decode("utf-8")
        except Exception:
            content = raw_bytes.decode("utf-8", errors="ignore")

        if content.strip() == "":
            raise HTTPException(status_code=400, detail="empty file")

        doc_id = str(uuid.uuid4())
        now = _now_utc()

        # stored_path is required in your schema; for MVP we map it to an upload uri
        stored_path = f"upload://{doc_id}/{filename}"

        doc_cols = set(_table_cols("documents"))
        doc_data: Dict[str, Any] = {}

        # required fields
        if "doc_id" in doc_cols:
            doc_data["doc_id"] = doc_id
        if "filename" in doc_cols:
            doc_data["filename"] = filename
        if "stored_path" in doc_cols:
            doc_data["stored_path"] = stored_path
        if "created_at" in doc_cols:
            doc_data["created_at"] = now
        if "doc_type" in doc_cols:
            doc_data["doc_type"] = "txt"

        # optional best-effort fields (only if exist)
        if "storage_uri" in doc_cols:
            doc_data["storage_uri"] = stored_path
        if "title" in doc_cols:
            doc_data["title"] = filename
        if "source_type" in doc_cols:
            doc_data["source_type"] = "upload"
        if "updated_at" in doc_cols:
            doc_data["updated_at"] = now
        if "metadata_json" in doc_cols:
            meta = {"filename": filename, "content_type": file.content_type, "bytes": len(raw_bytes)}
            doc_data["metadata_json"] = json.dumps(meta)

        _insert_one(db, "documents", doc_data)

        # Create consent for subject_id scoping (so user can access their doc)
        try:
            insp = inspect(engine)
            if "consents" in insp.get_table_names(schema="public"):
                consent_cols = set(_table_cols("consents"))
                consent_id = str(uuid.uuid4())
                consent_data = {"consent_id": consent_id, "doc_id": doc_id, "status": "granted", "created_at": now}
                if "subject_id" in consent_cols:
                    consent_data["subject_id"] = ident.subject_id
                if "user_id" in consent_cols:
                    consent_data["user_id"] = ident.subject_id
                if "scope" in consent_cols:
                    consent_data["scope"] = "full"
                if "upload_token" in consent_cols:
                    consent_data["upload_token"] = str(uuid.uuid4())
                _insert_one(db, "consents", {k: v for k, v in consent_data.items() if k in consent_cols})
        except Exception:
            pass  # Consents table might have different schema

        # chunks
        chunk_cols = set(_table_cols("chunks"))
        pieces = _chunk_text(content, chunk_size=chunk_size, overlap=overlap)

        created = 0
        for idx, (cs, ce, chunk_txt) in enumerate(pieces):
            row: Dict[str, Any] = {}

            # required fields (per your schema)
            if "chunk_id" in chunk_cols:
                row["chunk_id"] = str(uuid.uuid4())
            if "doc_id" in chunk_cols:
                row["doc_id"] = doc_id
            if "idx" in chunk_cols:
                row["idx"] = int(idx)
            if "char_start" in chunk_cols:
                row["char_start"] = int(cs)
            if "char_end" in chunk_cols:
                row["char_end"] = int(ce)
            if "snippet" in chunk_cols:
                row["snippet"] = _safe_snippet(chunk_txt, max_len=300)
            if "quote_hash" in chunk_cols:
                # For MVP: hash the chunk_text itself (package 3 can upgrade to hash of exact referenced span)
                row["quote_hash"] = _sha256_text(chunk_txt)
            if "created_at" in chunk_cols:
                row["created_at"] = now
            if "chunk_text" in chunk_cols:
                row["chunk_text"] = chunk_txt

            # optional
            if "stored_path" in chunk_cols:
                row["stored_path"] = stored_path
            if "storage_uri" in chunk_cols:
                row["storage_uri"] = stored_path

            _insert_one(db, "chunks", row)
            created += 1

        db.commit()
        return {"doc_id": doc_id, "chunks_created": int(created), "stored_path": stored_path}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"/documents/import failed: {type(e).__name__}: {e}")


# -----------------------------
# POST /documents/upload (TXT/DOCX/PDF with consent)
# -----------------------------
@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Query(default="demo", description="Document type: demo, synthetic, real"),
    user_id: str = Query(default="anonymous", description="User ID for consent tracking"),
    consent: bool = Query(default=True, description="User consent for processing"),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Upload a document (TXT, DOCX, or PDF) with consent tracking.
    
    This endpoint:
    1. Validates file type
    2. Creates document record
    3. Creates consent record
    4. Parses file into chunks
    5. Stores chunks with evidence pointers
    6. Optionally triggers async embedding job
    
    Supported formats: .txt, .docx, .pdf
    """
    try:
        from backend.app.parsers import parse_file_to_chunks
    except ImportError:
        from app.parsers import parse_file_to_chunks
    
    try:
        # Validate consent
        if not consent:
            raise HTTPException(status_code=400, detail="Consent is required for document processing")
        
        # Validate file
        filename = (file.filename or "uploaded").strip()
        ext = os.path.splitext(filename)[1].lower()
        
        if ext not in [".txt", ".docx", ".pdf"]:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported file type: {ext}. Supported: .txt, .docx, .pdf"
            )
        
        raw_bytes = await file.read()
        if len(raw_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty file")
        if len(raw_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)} MB)")
        _validate_magic(raw_bytes, ext)
        
        doc_id = str(uuid.uuid4())
        consent_id = str(uuid.uuid4())
        now = _now_utc()
        
        upload_dir = Path(__file__).parent.parent.parent / "uploads"
        upload_dir.mkdir(exist_ok=True)
        stored_filename = f"{doc_id}_{filename}"
        stored_path = str(upload_dir / stored_filename)
        
        # Save file to disk
        with open(stored_path, "wb") as f:
            f.write(raw_bytes)
        
        # Parse file into chunks
        try:
            chunks = parse_file_to_chunks(
                file_bytes=raw_bytes,
                filename=filename,
                min_chunk_len=50,
            )
        except ImportError as e:
            # Clean up saved file
            if os.path.exists(stored_path):
                os.remove(stored_path)
            raise HTTPException(status_code=500, detail=f"Parser not available: {e}")
        except Exception as e:
            if os.path.exists(stored_path):
                os.remove(stored_path)
            raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")
        
        if not chunks:
            if os.path.exists(stored_path):
                os.remove(stored_path)
            raise HTTPException(status_code=400, detail="File produced no valid chunks")
        
        # Create document record
        doc_cols = set(_table_cols("documents"))
        doc_data: Dict[str, Any] = {}
        
        if "doc_id" in doc_cols:
            doc_data["doc_id"] = doc_id
        if "filename" in doc_cols:
            doc_data["filename"] = filename
        if "stored_path" in doc_cols:
            doc_data["stored_path"] = stored_path
        if "created_at" in doc_cols:
            doc_data["created_at"] = now
        if "doc_type" in doc_cols:
            doc_data["doc_type"] = ext.lstrip(".")
        if "storage_uri" in doc_cols:
            doc_data["storage_uri"] = stored_path
        if "title" in doc_cols:
            doc_data["title"] = filename
        if "source_type" in doc_cols:
            doc_data["source_type"] = doc_type
        if "updated_at" in doc_cols:
            doc_data["updated_at"] = now
        if "metadata_json" in doc_cols:
            meta = {
                "filename": filename,
                "content_type": file.content_type,
                "bytes": len(raw_bytes),
                "user_id": user_id,
            }
            doc_data["metadata_json"] = json.dumps(meta)
        
        _insert_one(db, "documents", doc_data)
        
        # Create consent record (use savepoint to isolate failures)
        insp = inspect(engine)
        tables = set(insp.get_table_names(schema="public"))
        if "consents" in tables:
            try:
                nested = db.begin_nested()
                consent_sql = text("""
                    INSERT INTO consents (consent_id, user_id, doc_id, status, created_at)
                    VALUES (:consent_id, :user_id, :doc_id, 'granted', :created_at)
                """)
                db.execute(consent_sql, {
                    "consent_id": consent_id,
                    "user_id": ident.subject_id,
                    "doc_id": doc_id,
                    "created_at": now,
                })
                nested.commit()
            except Exception:
                pass
        
        # Insert chunks
        chunk_cols = set(_table_cols("chunks"))
        chunks_created = 0
        
        for ch in chunks:
            row: Dict[str, Any] = {}
            
            if "chunk_id" in chunk_cols:
                row["chunk_id"] = str(uuid.uuid4())
            if "doc_id" in chunk_cols:
                row["doc_id"] = doc_id
            if "idx" in chunk_cols:
                row["idx"] = int(ch.get("idx", chunks_created))
            if "char_start" in chunk_cols:
                row["char_start"] = int(ch.get("char_start", 0))
            if "char_end" in chunk_cols:
                row["char_end"] = int(ch.get("char_end", 0))
            if "snippet" in chunk_cols:
                row["snippet"] = ch.get("snippet", "")[:300]
            if "quote_hash" in chunk_cols:
                row["quote_hash"] = ch.get("quote_hash", "")
            if "created_at" in chunk_cols:
                row["created_at"] = now
            if "chunk_text" in chunk_cols:
                row["chunk_text"] = ch.get("chunk_text", "")
            if "section_path" in chunk_cols:
                row["section_path"] = ch.get("section_path")
            if "page_start" in chunk_cols:
                row["page_start"] = ch.get("page_start")
            if "page_end" in chunk_cols:
                row["page_end"] = ch.get("page_end")
            if "stored_path" in chunk_cols:
                row["stored_path"] = stored_path
            if "storage_uri" in chunk_cols:
                row["storage_uri"] = stored_path
            
            _insert_one(db, "chunks", row)
            chunks_created += 1
        
        # Create job for async embedding (use savepoint to isolate failures)
        job_id = None
        if "jobs" in tables:
            try:
                nested = db.begin_nested()
                job_id = str(uuid.uuid4())
                job_cols = set(_table_cols("jobs"))
                job_data = {"job_id": job_id, "doc_id": doc_id, "status": "pending", "attempts": 0, "created_at": now}
                if "job_type" in job_cols:
                    job_data["job_type"] = "embed"
                _insert_one(db, "jobs", job_data)
                nested.commit()
            except Exception:
                job_id = None
        
        db.commit()
        
        return {
            "doc_id": doc_id,
            "filename": filename,
            "doc_type": ext.lstrip("."),
            "chunks_created": chunks_created,
            "consent_id": consent_id,
            "job_id": job_id,
            "stored_path": stored_path,
            "message": "Document uploaded and parsed successfully.",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"/documents/upload failed: {type(e).__name__}: {e}")


# -----------------------------
# POST /documents/{doc_id}/reindex
# -----------------------------
@router.post("/{doc_id}/reindex")
def reindex_document(
    doc_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Trigger re-indexing of document embeddings.
    Creates a job entry for the worker to process.
    """
    try:
        check_doc_access(ident, doc_id, db)
        doc_sql = text("SELECT doc_id FROM documents WHERE doc_id = :doc_id")
        doc = db.execute(doc_sql, {"doc_id": doc_id}).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Create job
        job_id = str(uuid.uuid4())
        now = _now_utc()
        
        job_sql = text("""
            INSERT INTO jobs (job_id, doc_id, status, attempts, created_at)
            VALUES (:job_id, :doc_id, 'pending', 0, :created_at)
        """)
        db.execute(job_sql, {
            "job_id": job_id,
            "doc_id": doc_id,
            "created_at": now,
        })
        db.commit()
        
        return {
            "doc_id": doc_id,
            "job_id": job_id,
            "status": "pending",
            "message": "Reindex job created. Worker will process embeddings.",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"/documents/{doc_id}/reindex failed: {type(e).__name__}: {e}")


# -----------------------------
# POST /documents/upload_multimodal
# -----------------------------
@router.post("/upload_multimodal")
async def upload_multimodal_document(
    file: UploadFile = File(...),
    doc_type: str = Query(default="demo", description="Document type"),
    user_id: str = Query(default="anonymous", description="User ID"),
    consent: bool = Query(default=True, description="User consent"),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Upload any supported file type with multimodal parsing.
    
    Supported formats:
    - Documents: TXT, DOCX, PDF, PPTX
    - Images: JPG, PNG, WEBP, BMP, TIFF, GIF (with OCR)
    - Video/Audio: MP4, WEBM, MOV, MP3, WAV, M4A (with transcription)
    - Code: PY, JS, TS, JAVA, CPP, GO, RS, etc.
    
    For images and videos, the system will:
    1. Extract text via OCR or transcription
    2. Store original file for vision model access
    3. Generate embeddings from extracted text
    """
    try:
        from backend.app.parsers_multimodal import parse_multimodal_file, SUPPORTED_EXTENSIONS
    except ImportError:
        from app.parsers_multimodal import parse_multimodal_file, SUPPORTED_EXTENSIONS
    
    if not consent:
        raise HTTPException(status_code=400, detail="Consent is required")
    
    filename = (file.filename or "uploaded").strip()
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS.keys()))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Supported: {supported}"
        )
    
    raw_bytes = await file.read()
    if len(raw_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)} MB)")
    _validate_magic(raw_bytes, ext)

    # Idempotency: same user + same file content returns existing doc when already granted.
    content_hash = _sha256_bytes(raw_bytes)
    existing = None
    try:
        doc_cols = set(_table_cols("documents"))
        tables_now = set(inspect(engine).get_table_names(schema="public"))
        if "metadata_json" in doc_cols and "consents" in tables_now:
            existing = db.execute(
                text("""
                    SELECT d.doc_id, d.filename
                    FROM documents d
                    JOIN consents c ON c.doc_id = d.doc_id::text
                    WHERE c.user_id = :uid
                      AND c.status = 'granted'
                      AND (d.metadata_json::jsonb ->> 'content_hash') = :content_hash
                    ORDER BY d.created_at DESC
                    LIMIT 1
                """),
                {"uid": ident.subject_id, "content_hash": content_hash},
            ).mappings().first()
    except Exception:
        db.rollback()
        existing = None
    if existing:
        chunks_count = db.execute(
            text("SELECT COUNT(*) FROM chunks WHERE doc_id = :doc_id"),
            {"doc_id": str(existing["doc_id"])},
        ).scalar() or 0
        return {
            "doc_id": str(existing["doc_id"]),
            "filename": existing.get("filename") or filename,
            "media_type": SUPPORTED_EXTENSIONS.get(ext, "unknown"),
            "chunks_created": int(chunks_count),
            "duplicate_of": str(existing["doc_id"]),
            "message": "Duplicate content detected; reused existing document.",
        }
    
    doc_id = str(uuid.uuid4())
    consent_id = str(uuid.uuid4())
    now = _now_utc()
    
    # Save file
    upload_dir = Path(__file__).parent.parent.parent / "uploads"
    upload_dir.mkdir(exist_ok=True)
    stored_filename = f"{doc_id}_{filename}"
    stored_path = str(upload_dir / stored_filename)
    
    with open(stored_path, "wb") as f:
        f.write(raw_bytes)
    
    # Parse with multimodal parser
    try:
        result = parse_multimodal_file(
            file_bytes=raw_bytes,
            filename=filename,
            min_chunk_len=30,
        )
    except Exception as e:
        if os.path.exists(stored_path):
            os.remove(stored_path)
        raise HTTPException(status_code=400, detail=f"Failed to parse: {e}")
    
    chunks = result.get("chunks", [])
    media_type = result.get("media_type", "unknown")
    metadata = result.get("metadata", {})
    vision_data = result.get("vision_data")
    
    if not chunks:
        # For media files, create a placeholder chunk
        chunks = [{
            "idx": 0,
            "char_start": 0,
            "char_end": 0,
            "chunk_text": f"[{media_type.upper()} file: {filename}]",
            "snippet": f"[{media_type.upper()} file]",
            "quote_hash": _sha256_text(filename),
        }]
    
    # Create document record
    doc_cols = set(_table_cols("documents"))
    doc_data: Dict[str, Any] = {}
    
    if "doc_id" in doc_cols:
        doc_data["doc_id"] = doc_id
    if "filename" in doc_cols:
        doc_data["filename"] = filename
    if "stored_path" in doc_cols:
        doc_data["stored_path"] = stored_path
    if "created_at" in doc_cols:
        doc_data["created_at"] = now
    if "doc_type" in doc_cols:
        doc_data["doc_type"] = media_type
    if "source_type" in doc_cols:
        doc_data["source_type"] = doc_type
    if "metadata_json" in doc_cols:
        meta = {
            "filename": filename,
            "content_type": file.content_type,
            "bytes": len(raw_bytes),
            "user_id": ident.subject_id,
            "media_type": media_type,
            "content_hash": content_hash,
            **metadata,
        }
        if vision_data:
            meta["has_vision_data"] = True
        doc_data["metadata_json"] = json.dumps(meta)
    
    _insert_one(db, "documents", doc_data)
    
    # Create consent (use savepoint to avoid poisoning the transaction)
    insp_mm = inspect(engine)
    tables_mm = set(insp_mm.get_table_names(schema="public"))
    if "consents" in tables_mm:
        try:
            nested = db.begin_nested()
            db.execute(text("""
                INSERT INTO consents (consent_id, user_id, doc_id, status, created_at)
                VALUES (:consent_id, :user_id, :doc_id, 'granted', :created_at)
            """), {
                "consent_id": consent_id,
                "user_id": ident.subject_id,
                "doc_id": doc_id,
                "created_at": now,
            })
            nested.commit()
        except Exception:
            pass
    
    # Insert chunks
    chunk_cols = set(_table_cols("chunks"))
    chunks_created = 0
    
    for ch in chunks:
        row: Dict[str, Any] = {}
        
        if "chunk_id" in chunk_cols:
            row["chunk_id"] = str(uuid.uuid4())
        if "doc_id" in chunk_cols:
            row["doc_id"] = doc_id
        if "idx" in chunk_cols:
            row["idx"] = int(ch.get("idx", chunks_created))
        if "char_start" in chunk_cols:
            row["char_start"] = int(ch.get("char_start", 0))
        if "char_end" in chunk_cols:
            row["char_end"] = int(ch.get("char_end", 0))
        if "snippet" in chunk_cols:
            row["snippet"] = (ch.get("snippet") or "")[:300]
        if "quote_hash" in chunk_cols:
            row["quote_hash"] = ch.get("quote_hash", "")
        if "created_at" in chunk_cols:
            row["created_at"] = now
        if "chunk_text" in chunk_cols:
            row["chunk_text"] = ch.get("chunk_text", "")
        if "section_path" in chunk_cols:
            row["section_path"] = ch.get("section_path")
        if "page_start" in chunk_cols:
            row["page_start"] = ch.get("page_start")
        if "page_end" in chunk_cols:
            row["page_end"] = ch.get("page_end")
        
        _insert_one(db, "chunks", row)
        chunks_created += 1
    
    # Create embedding job (use savepoint to avoid poisoning the transaction)
    job_id = None
    if "jobs" in tables_mm:
        try:
            nested = db.begin_nested()
            job_id = str(uuid.uuid4())
            job_cols = set(_table_cols("jobs"))
            job_data = {"job_id": job_id, "doc_id": doc_id, "status": "pending", "attempts": 0, "created_at": now}
            if "job_type" in job_cols:
                job_data["job_type"] = "embed"
            _insert_one(db, "jobs", job_data)
            nested.commit()
        except Exception:
            job_id = None
    
    db.commit()
    
    return {
        "doc_id": doc_id,
        "filename": filename,
        "media_type": media_type,
        "chunks_created": chunks_created,
        "consent_id": consent_id,
        "job_id": job_id,
        "stored_path": stored_path,
        "has_vision_data": vision_data is not None,
        "metadata": metadata,
        "message": f"{media_type.capitalize()} file uploaded and processed.",
    }