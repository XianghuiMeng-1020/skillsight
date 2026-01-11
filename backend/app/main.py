import os
import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing. Put it in backend/.env")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SkillSight API", version="0.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    ddl = """
    CREATE TABLE IF NOT EXISTS documents (
        doc_id UUID PRIMARY KEY,
        filename TEXT NOT NULL,
        stored_path TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    );

    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id UUID PRIMARY KEY,
        doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
        idx INTEGER NOT NULL,
        char_start INTEGER NOT NULL,
        char_end INTEGER NOT NULL,
        snippet TEXT NOT NULL,
        quote_hash TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"ok": True, "db": "ok"}

def _hash_quote(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _make_snippet(s: str, max_len: int = 280) -> str:
    ss = " ".join(s.split())
    return ss if len(ss) <= max_len else ss[: max_len - 3] + "..."

def _split_into_paragraph_chunks(t: str) -> List[Tuple[int, int, str]]:
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    chunks: List[Tuple[int, int, str]] = []
    n = len(t)
    i = 0

    while i < n:
        while i < n and t[i] == "\n":
            i += 1
        if i >= n:
            break

        start = i
        while i < n:
            if t[i] == "\n" and (i + 1 < n and t[i + 1] == "\n"):
                break
            i += 1

        end = i
        chunk_text = t[start:end].strip()
        if chunk_text:
            chunks.append((start, end, chunk_text))

        while i < n and t[i] == "\n":
            i += 1

    if not chunks and t.strip():
        chunks = [(0, n, t.strip())]

    return chunks

def create_chunks_for_document(doc_id: str, raw_text: str):
    parts = _split_into_paragraph_chunks(raw_text)
    now = datetime.now(timezone.utc).isoformat()

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM chunks WHERE doc_id = (:doc_id)::uuid"), {"doc_id": doc_id})

        for idx, (cs, ce, chunk_text) in enumerate(parts):
            chunk_id = str(uuid.uuid4())
            conn.execute(
                text("""
                    INSERT INTO chunks (chunk_id, doc_id, idx, char_start, char_end, snippet, quote_hash, created_at)
                    VALUES ((:chunk_id)::uuid, (:doc_id)::uuid, :idx, :char_start, :char_end, :snippet, :quote_hash, :created_at)
                """),
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "idx": idx,
                    "char_start": cs,
                    "char_end": ce,
                    "snippet": _make_snippet(chunk_text),
                    "quote_hash": _hash_quote(chunk_text),
                    "created_at": now,
                },
            )

@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    if not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Week2 only supports .txt files")

    doc_id = str(uuid.uuid4())
    safe_name = f"{doc_id}_{Path(file.filename).name}"
    stored_path = UPLOAD_DIR / safe_name

    try:
        content = await file.read()
        stored_path.write_bytes(content)
        raw_text = content.decode("utf-8", errors="ignore")

        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO documents (doc_id, filename, stored_path, created_at)
                    VALUES ((:doc_id)::uuid, :filename, :stored_path, :created_at)
                """),
                {
                    "doc_id": doc_id,
                    "filename": file.filename,
                    "stored_path": str(stored_path),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        create_chunks_for_document(doc_id, raw_text)

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}") from e

    return {"doc_id": doc_id, "filename": file.filename}

@app.get("/documents")
def list_documents(limit: int = 20):
    limit = max(1, min(limit, 100))
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT doc_id, filename, created_at
                FROM documents
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).mappings().all()
    return {"items": [dict(r) for r in rows]}

@app.get("/documents/{doc_id}/chunks")
def list_chunks(doc_id: str, limit: int = 200):
    limit = max(1, min(limit, 500))
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT chunk_id, doc_id, idx, char_start, char_end, snippet, quote_hash, created_at
                FROM chunks
                WHERE doc_id = (:doc_id)::uuid
                ORDER BY idx ASC
                LIMIT :limit
            """),
            {"doc_id": doc_id, "limit": limit},
        ).mappings().all()
    return {"items": [dict(r) for r in rows]}

@app.post("/documents/{doc_id}/rechunk")
def rechunk_document(doc_id: str):
    # Load stored file path
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT stored_path FROM documents WHERE doc_id = (:doc_id)::uuid"),
            {"doc_id": doc_id},
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    stored_path = row["stored_path"]
    try:
        raw_bytes = Path(stored_path).read_bytes()
        raw_text = raw_bytes.decode("utf-8", errors="ignore")
        create_chunks_for_document(doc_id, raw_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rechunk failed: {e}") from e

    with engine.connect() as conn:
        n_chunks = conn.execute(
            text("SELECT count(*) FROM chunks WHERE doc_id = (:doc_id)::uuid"),
            {"doc_id": doc_id},
        ).scalar_one()

    return {"doc_id": doc_id, "n_chunks": int(n_chunks)}
