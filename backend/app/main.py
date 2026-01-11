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
        chunk_text TEXT NOT NULL,
        snippet TEXT NOT NULL,
        quote_hash TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
    ALTER TABLE chunks ADD COLUMN IF NOT EXISTS chunk_text TEXT;
    UPDATE chunks SET chunk_text = snippet WHERE chunk_text IS NULL;
    ALTER TABLE chunks ALTER COLUMN chunk_text SET NOT NULL;

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
                    INSERT INTO chunks (chunk_id, doc_id, idx, char_start, char_end, chunk_text, snippet, quote_hash, created_at)
                    VALUES ((:chunk_id)::uuid, (:doc_id)::uuid, :idx, :char_start, :char_end, :chunk_text, :snippet, :quote_hash, :created_at)
                """),
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "idx": idx,
                    "char_start": cs,
                    "char_end": ce,
                    "chunk_text": chunk_text,
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

@app.post("/search/evidence")
def search_evidence(payload: dict):
    """
    BM25 baseline (Week3 upgrade):
    - payload: {"query": "...", "doc_id": optional, "k": optional}
    - returns: top-k chunks ranked by BM25 on snippet text
    """
    import math
    import re as _re

    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Missing query")

    doc_id = payload.get("doc_id")
    k = int(payload.get("k") or 10)
    k = max(1, min(k, 50))

    # Tokenization (simple + robust)
    def tokenize(text: str):
        text = text.lower()
        toks = _re.findall(r"[a-z0-9]+", text)
        stop = {
            "the","a","an","and","or","to","of","in","on","for","with","is","are","was","were","be","as","by",
            "it","this","that","from","at","we","you","they","he","she","i","me","my","our","your","their"
        }
        toks = [t for t in toks if t not in stop]
        toks = [t for t in toks if len(t) >= 2]
        return toks

    q_tokens = tokenize(query)
    if not q_tokens:
        raise HTTPException(status_code=400, detail="Query too short after filtering")

    # Pull candidate chunks (MVP: use snippet only)
    sql = """
        SELECT chunk_id, doc_id, idx, char_start, char_end, chunk_text, snippet, created_at
        FROM chunks
        {where}
        ORDER BY created_at DESC
        LIMIT 2000
    """
    where = ""
    params = {}
    if doc_id:
        where = "WHERE doc_id = (:doc_id)::uuid"
        params["doc_id"] = doc_id

    with engine.connect() as conn:
        rows = conn.execute(text(sql.format(where=where)), params).mappings().all()

    # Build corpus stats for BM25 within candidates
    # docs: list of dicts with tokens + tf map
    docs = []
    df = {}  # document frequency per term
    total_len = 0

    for r in rows:
        snippet = (r.get("chunk_text") or r.get("snippet") or "")
        toks = tokenize(snippet)
        # term frequency
        tf = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        # update df (unique terms per doc)
        for t in set(tf.keys()):
            df[t] = df.get(t, 0) + 1

        doc_len = len(toks)
        total_len += doc_len
        docs.append((dict(r), tf, doc_len))

    N = len(docs)
    if N == 0:
        return {"items": [], "query_tokens": q_tokens, "note": "No chunks available in scope."}

    avgdl = total_len / N if N > 0 else 1.0

    # BM25 parameters (standard-ish defaults)
    k1 = 1.5
    b = 0.75

    def idf(term: str) -> float:
        # Smoothed IDF. +1 keeps it positive even for common terms.
        dft = df.get(term, 0)
        return math.log(((N - dft + 0.5) / (dft + 0.5)) + 1.0)

    scored = []
    for meta, tf, dl in docs:
        score = 0.0
        for term in q_tokens:
            if term not in tf:
                continue
            f = tf[term]
            denom = f + k1 * (1.0 - b + b * (dl / avgdl if avgdl > 0 else 1.0))
            score += idf(term) * (f * (k1 + 1.0) / (denom if denom != 0 else 1.0))

        if score > 0:
            meta["score"] = float(score)
            meta.pop("chunk_text", None)
            scored.append(meta)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return {"items": scored[:k], "query_tokens": q_tokens, "scoring": "BM25", "N": N, "avgdl": avgdl}


# -------------------------
# Skill Registry (v0)
# -------------------------
import json
from functools import lru_cache

SKILLS_PATH = Path(__file__).resolve().parent.parent / "data" / "skills.json"

@lru_cache(maxsize=1)
def load_skills() -> list:
    if not SKILLS_PATH.exists():
        return []
    return json.loads(SKILLS_PATH.read_text(encoding="utf-8"))

def get_skill_by_id(skill_id: str) -> dict | None:
    for sk in load_skills():
        if sk.get("skill_id") == skill_id:
            return sk
    return None

@app.get("/skills")
def list_skills():
    return {"items": load_skills()}

@app.get("/skills/{skill_id}")
def get_skill(skill_id: str):
    sk = get_skill_by_id(skill_id)
    if not sk:
        raise HTTPException(status_code=404, detail="Skill not found")
    return sk

@app.post("/search/skill_evidence")
def search_skill_evidence(payload: dict):
    """
    Payload:
      {"skill_id": "...", "doc_id": optional, "k": optional}
    Behavior:
      build query from canonical_name + definition + aliases, then call /search/evidence BM25.
    """
    skill_id = (payload.get("skill_id") or "").strip()
    if not skill_id:
        raise HTTPException(status_code=400, detail="Missing skill_id")

    sk = get_skill_by_id(skill_id)
    if not sk:
        raise HTTPException(status_code=404, detail="Skill not found")

    doc_id = payload.get("doc_id")
    k = int(payload.get("k") or 10)

    canonical = sk.get("canonical_name") or ""
    definition = sk.get("definition") or ""
    aliases = sk.get("aliases") or []
    alias_text = " ".join([a for a in aliases if isinstance(a, str)])

    # You can tweak this template later (this is v0)
    query = f"{canonical}. {definition} Aliases: {alias_text}".strip()

    # Reuse the existing BM25 endpoint function
    return {
        **search_evidence({"query": query, "doc_id": doc_id, "k": k}),
        "skill_id": skill_id,
        "generated_query": query
    }
