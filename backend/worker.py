import os
import uuid
import hashlib
from datetime import datetime, timezone

from rq import Worker
from redis import Redis
from sqlalchemy import text

# Only reuse what is guaranteed to exist in app.main
from app.main import engine, parse_docx_to_chunks, parse_pdf_to_chunks
from app.vector_store import get_client, ensure_collection, upsert_points, delete_by_doc_id
from app.embeddings import embed_texts, emb_dim
from qdrant_client.http import models as qm

REDIS_HOST = "localhost"
REDIS_PORT = 6379
QUEUE_NAME = "skillsight"

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _make_snippet(text: str, n: int = 220) -> str:
    t = (text or "").strip().replace("\n", " ")
    return t[:n] + ("..." if len(t) > n else "")

def _hash_quote(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

def ensure_chunks_table():
    # defensive DDL: doesn't break if already exists
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

def _parse_txt_to_chunks(text: str):
    t = (text or "").replace("\r\n", "\n")
    chunks = []
    cursor = 0
    for part in t.split("\n\n"):
        part_raw = part
        part_strip = part_raw.strip()
        pos = t.find(part_raw, cursor)
        if pos == -1:
            pos = cursor
        cs = pos
        ce = pos + len(part_raw)
        cursor = ce + 2
        if part_strip:
            chunks.append({
                "char_start": cs,
                "char_end": ce,
                "chunk_text": part_strip,
                "section_path": None,
                "page_start": None,
                "page_end": None
            })
    return chunks

def update_job(job_id: str, status: str, attempts: int, last_error: str | None = None):
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
    ext = os.path.splitext(filename.lower())[1]

    # Parse
    if ext == ".txt":
        txt = Path(stored_path).read_text(encoding="utf-8", errors="ignore")
        chunk_dicts = _parse_txt_to_chunks(txt)
    elif ext == ".docx":
        chunk_dicts = parse_docx_to_chunks(stored_path)
    elif ext == ".pdf":
        chunk_dicts = parse_pdf_to_chunks(stored_path)
    else:
        raise RuntimeError(f"Unsupported extension for worker: {ext}")

    # Ensure table
    ensure_chunks_table()

    # Replace chunks in DB for doc
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM chunks WHERE doc_id = (:doc_id)::uuid"), {"doc_id": doc_id})
        for idx, ch in enumerate(chunk_dicts):
            ct = (ch.get("chunk_text") or "").strip()
            if not ct:
                continue
            chunk_id = str(uuid.uuid4())
            snippet = _make_snippet(ct)
            quote_hash = _hash_quote(ct)
            conn.execute(
                text("""
                    INSERT INTO chunks (chunk_id, doc_id, idx, char_start, char_end, chunk_text, snippet, quote_hash, created_at, section_path, page_start, page_end)
                    VALUES ((:chunk_id)::uuid, (:doc_id)::uuid, :idx, :char_start, :char_end, :chunk_text, :snippet, :quote_hash, now(), :section_path, :page_start, :page_end)
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
    client = get_client()
    ensure_collection(client, emb_dim())
    delete_by_doc_id(client, doc_id)

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT chunk_id::text as chunk_id, doc_id::text as doc_id, idx, snippet, section_path, page_start, page_end, created_at, chunk_text
                FROM chunks
                WHERE doc_id = (:doc_id)::uuid
                ORDER BY idx ASC
            """),
            {"doc_id": doc_id},
        ).mappings().all()

    vecs = embed_texts([r["chunk_text"] for r in rows])
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
        upsert_points(client, points)

def run_job(doc_id: str, job_id: str):
    with engine.connect() as conn:
        r = conn.execute(text("SELECT attempts FROM jobs WHERE job_id = (:job_id)::uuid"), {"job_id": job_id}).first()
        attempts = int(r[0]) if r else 0
    attempts += 1

    update_job(job_id, "running", attempts, None)
    try:
        process_doc(doc_id, job_id)
        update_job(job_id, "succeeded", attempts, None)
    except Exception as e:
        update_job(job_id, "failed", attempts, f"{type(e).__name__}: {e}")
        raise

if __name__ == "__main__":
    redis_conn = Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
    w = Worker([QUEUE_NAME], connection=redis_conn)
    w.work()
