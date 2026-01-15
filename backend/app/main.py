import os
import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

from fastapi.responses import JSONResponse
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from app.rbac import get_current_user, require_doc_access
from app.change_log import diff_role_readiness, log_change, list_changes
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing. Put it in backend/.env")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SKILLS_PATH = Path(__file__).resolve().parent.parent / "data" / "skills.json"

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
        created_at TIMESTAMPTZ NOT NULL,
        doc_type TEXT NOT NULL
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
        created_at TIMESTAMPTZ NOT NULL,
        doc_type TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
    ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_type TEXT;
    UPDATE documents SET doc_type = 'demo' WHERE doc_type IS NULL;
    ALTER TABLE documents ALTER COLUMN doc_type SET NOT NULL;
    ALTER TABLE documents ADD COLUMN IF NOT EXISTS subject_id TEXT;


    ALTER TABLE chunks ADD COLUMN IF NOT EXISTS chunk_text TEXT;
    UPDATE chunks SET chunk_text = snippet WHERE chunk_text IS NULL;
    ALTER TABLE chunks ALTER COLUMN chunk_text SET NOT NULL;
    ALTER TABLE chunks ADD COLUMN IF NOT EXISTS section_path TEXT;
    ALTER TABLE chunks ADD COLUMN IF NOT EXISTS page_start INTEGER;
    ALTER TABLE chunks ADD COLUMN IF NOT EXISTS page_end INTEGER;


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
async def upload_document(request: Request, 
    doc_id: str = Form(...),
    upload_token: str = Form(...),    doc_type: str = Form("demo"),
    file: UploadFile = File(...)
):
    """
    Strict upload:
      - requires consent/start first (doc_id + upload_token)
      - requires subject_id (owner)
      - blocks upload if consent not granted or token mismatch
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    # strict: require granted consent + valid upload_token
    require_upload_token(doc_id, upload_token)

    user = get_current_user(request)
    subject_id = user['subject_id']

    allowed_doc_types = {"demo", "synthetic", "real"}
    if doc_type not in allowed_doc_types:
        raise HTTPException(status_code=400, detail="Invalid doc_type. Use demo/synthetic/real")

    lower = file.filename.lower()
    if not (lower.endswith(".txt") or lower.endswith(".docx") or lower.endswith(".pdf")):
        raise HTTPException(status_code=400, detail="Supported: .txt, .docx, .pdf")

    # Use doc_id from consent/start (do NOT generate a new one)
    safe_name = f"{doc_id}_{Path(file.filename).name}"
    stored_path = UPLOAD_DIR / safe_name

    try:
        content = await file.read()
        stored_path.write_bytes(content)

        # Insert / upsert document row (doc_id fixed by consent)
        with engine.begin() as conn:
            # if a row exists for same doc_id, replace stored_path/filename/doc_type/subject_id
            conn.execute(
                text("""
                    DELETE FROM documents WHERE doc_id = (:doc_id)::uuid
                """),
                {"doc_id": doc_id},
            )
            conn.execute(
                text("""
                    INSERT INTO documents (doc_id, filename, stored_path, created_at, doc_type, subject_id)
                    VALUES ((:doc_id)::uuid, :filename, :stored_path, :created_at, :doc_type, :subject_id)
                """),
                {
                    "doc_id": doc_id,
                    "filename": file.filename,
                    "stored_path": str(stored_path),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "doc_type": doc_type,
                    "subject_id": subject_id,
                },
            )

        # Delete old chunks for this doc_id (idempotent)
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM chunks WHERE doc_id = (:doc_id)::uuid"), {"doc_id": doc_id})

        # Parse + write chunks
        if lower.endswith(".txt"):
            raw_text = content.decode("utf-8", errors="ignore")
            create_chunks_for_document(doc_id, raw_text)

        elif lower.endswith(".docx"):
            parsed = parse_docx_to_chunks(str(stored_path))
            with engine.begin() as conn:
                for idx, ch in enumerate(parsed):
                    conn.execute(
                        text("""
                            INSERT INTO chunks
                            (chunk_id, doc_id, idx, char_start, char_end,
                             chunk_text, snippet, quote_hash, created_at,
                             section_path, page_start, page_end)
                            VALUES
                            ((:chunk_id)::uuid, (:doc_id)::uuid, :idx, :char_start, :char_end,
                             :chunk_text, :snippet, :quote_hash, :created_at,
                             :section_path, :page_start, :page_end)
                        """),
                        {
                            "chunk_id": str(uuid.uuid4()),
                            "doc_id": doc_id,
                            "idx": idx,
                            "char_start": ch["char_start"],
                            "char_end": ch["char_end"],
                            "chunk_text": ch["chunk_text"],
                            "snippet": _make_snippet(ch["chunk_text"]),
                            "quote_hash": _hash_quote(ch["chunk_text"]),
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "section_path": ch.get("section_path"),
                            "page_start": None,
                            "page_end": None,
                        },
                    )

        elif lower.endswith(".pdf"):
            parsed = parse_pdf_to_chunks(str(stored_path))
            if not parsed:
                raise HTTPException(status_code=400, detail="PDF has no extractable text (OCR not supported).")
            with engine.begin() as conn:
                for idx, ch in enumerate(parsed):
                    conn.execute(
                        text("""
                            INSERT INTO chunks
                            (chunk_id, doc_id, idx, char_start, char_end,
                             chunk_text, snippet, quote_hash, created_at,
                             section_path, page_start, page_end)
                            VALUES
                            ((:chunk_id)::uuid, (:doc_id)::uuid, :idx, :char_start, :char_end,
                             :chunk_text, :snippet, :quote_hash, :created_at,
                             :section_path, :page_start, :page_end)
                        """),
                        {
                            "chunk_id": str(uuid.uuid4()),
                            "doc_id": doc_id,
                            "idx": idx,
                            "char_start": ch["char_start"],
                            "char_end": ch["char_end"],
                            "chunk_text": ch["chunk_text"],
                            "snippet": _make_snippet(ch["chunk_text"]),
                            "quote_hash": _hash_quote(ch["chunk_text"]),
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "section_path": None,
                            "page_start": ch.get("page_start"),
                            "page_end": ch.get("page_end"),
                        },
                    )

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}") from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}") from e

    return {"doc_id": doc_id, "filename": file.filename, "doc_type": doc_type, "subject_id": subject_id}

@app.get("/documents")
def list_documents(limit: int = 20):
    limit = max(1, min(limit, 100))
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT doc_id, filename, created_at, doc_type
                FROM documents
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).mappings().all()
    return {"items": [dict(r) for r in rows]}

@app.get("/documents/{doc_id}/chunks")
def list_chunks(doc_id: str, request: Request, limit: int = 200):
    """
    Strict read:
      - doc_id must be UUID
      - requires granted consent
      - requires RBAC doc ownership for students
      - returns v1 fields: section_path/page_start/page_end
    """
    import uuid as _uuid

    try:
        _uuid.UUID(doc_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid doc_id format")

    # Strict: consent must be granted
    require_consent_granted(doc_id)

    # RBAC: student must own document; staff/admin can read all
    user = get_current_user(request)
    require_doc_access(engine, user, doc_id)

    # Strict: doc must exist
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM documents WHERE doc_id = (:doc_id)::uuid"),
            {"doc_id": doc_id},
        ).first()
    if not exists:
        raise HTTPException(status_code=404, detail="Document not found")

    limit = max(1, min(limit, 500))
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT chunk_id, doc_id, idx, char_start, char_end,
                       snippet, quote_hash, created_at,
                       section_path, page_start, page_end
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
    BM25 evidence retrieval (Decision 1 baseline).
    Payload:
      {
        "query": "...",
        "doc_id": optional,
        "k": optional (default 10),
        "include_breakdown": optional bool (default false)
      }

    Notes:
      - `score` is a retrieval ranking score (BM25), NOT a probability/confidence.
      - If include_breakdown=true, returns `score_meta` per item with token-level contributions.
      - Future "confidence" can be added as a separate field without breaking this schema.
    """
    import math
    import re as _re

    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Missing query")

    doc_id = payload.get("doc_id")
    k = int(payload.get("k") or 10)
    k = max(1, min(k, 50))
    include_breakdown = bool(payload.get("include_breakdown") or False)

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

    # Count duplicates in query so behavior matches previous loop-over-tokens
    q_counts = {}
    for t in q_tokens:
        q_counts[t] = q_counts.get(t, 0) + 1

    # Pull candidate chunks (BM25 uses chunk_text; snippet is for UI)
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

    # Build corpus stats within current scope
    docs = []          # list of (meta, tf, dl)
    df = {}            # term -> document frequency
    total_len = 0

    for r in rows:
        text_for_scoring = (r.get("chunk_text") or r.get("snippet") or "")
        toks = tokenize(text_for_scoring)

        tf = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1

        for t in set(tf.keys()):
            df[t] = df.get(t, 0) + 1

        dl = len(toks)
        total_len += dl
        docs.append((dict(r), tf, dl))

    N = len(docs)
    if N == 0:
        return {"items": [], "query_tokens": q_tokens, "scoring": "BM25", "note": "No chunks available in scope."}

    avgdl = total_len / N if N > 0 else 1.0

    # BM25 params
    k1 = 1.5
    b = 0.75

    def idf(term: str) -> float:
        dft = df.get(term, 0)
        return math.log(((N - dft + 0.5) / (dft + 0.5)) + 1.0)

    scored = []
    for meta, tf, dl in docs:
        score = 0.0
        breakdown = []  # filled only if include_breakdown

        for term, q_count in q_counts.items():
            f = tf.get(term, 0)
            if f <= 0:
                if include_breakdown:
                    breakdown.append({
                        "term": term,
                        "query_count": q_count,
                        "tf": 0,
                        "idf": idf(term),
                        "base": 0.0,
                        "contrib": 0.0
                    })
                continue

            denom = f + k1 * (1.0 - b + b * (dl / avgdl if avgdl > 0 else 1.0))
            base = idf(term) * (f * (k1 + 1.0) / (denom if denom != 0 else 1.0))
            contrib = q_count * base
            score += contrib

            if include_breakdown:
                breakdown.append({
                    "term": term,
                    "query_count": q_count,
                    "tf": f,
                    "idf": idf(term),
                    "base": base,        # per-occurrence
                    "contrib": contrib   # includes query_count weighting
                })

        if score > 0:
            meta["score"] = float(score)  # keep backward compat with UI
            meta.pop("chunk_text", None)  # never return full text in API payload

            # score_meta is the expandable place for future changes
            meta["score_meta"] = {
                "type": "retrieval_bm25",
                "k1": k1,
                "b": b,
                "dl": dl,
                "avgdl": avgdl,
                "N": N,
            }
            if include_breakdown:
                meta["score_meta"]["breakdown"] = breakdown

            scored.append(meta)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return {
        "items": scored[:k],
        "query_tokens": q_tokens,
        "scoring": "BM25",
        "N": N,
        "avgdl": avgdl,
        "include_breakdown": include_breakdown
    }

@app.get("/skills")
def list_skills():
    items = load_skills()
    return {"items": items}


@app.get("/skills_debug")
def skills_debug():
    items = load_skills()
    return {
        "skills_path": str(SKILLS_PATH),
        "exists": bool(SKILLS_PATH.exists()),
        "count": len(items),
        "first_skill_id": items[0].get("skill_id") if items else None,
    }

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
      {"skill_id": "...", "doc_id": optional, "k": optional, "include_breakdown": optional}
    Builds a query from skill definition + aliases and calls /search/evidence (BM25).
    """
    try:
        skill_id = (payload.get("skill_id") or "").strip()
        if not skill_id:
            raise HTTPException(status_code=400, detail="Missing skill_id")

        sk = get_skill_by_id(skill_id)
        if not sk:
            raise HTTPException(status_code=404, detail="Skill not found")

        doc_id = payload.get("doc_id")
        k = int(payload.get("k") or 10)
        k = max(1, min(k, 50))
        include_breakdown = bool(payload.get("include_breakdown") or False)

        canonical = sk.get("canonical_name") or ""
        definition = sk.get("definition") or ""
        aliases = sk.get("aliases") or []
        alias_text = " ".join([a for a in aliases if isinstance(a, str)])

        generated_query = f"{canonical}. {definition} Aliases: {alias_text}".strip()

        result = search_evidence({
            "query": generated_query,
            "doc_id": doc_id,
            "k": k,
            "include_breakdown": include_breakdown
        })

        result["skill_id"] = skill_id
        result["generated_query"] = generated_query
        return result

    except HTTPException:
        # pass through expected HTTP errors
        raise
    except Exception as e:
        # Force JSON detail for ANY unexpected error (dev-friendly)
        raise HTTPException(status_code=500, detail=f"skill_evidence UNHANDLED: {type(e).__name__}: {e}")


# ---- Skill helper (v0) ----
def get_skill_by_id(skill_id: str):
    try:
        skills = load_skills()
    except Exception:
        skills = []
    for sk in skills:
        if isinstance(sk, dict) and sk.get("skill_id") == skill_id:
            return sk
    return None


# -------------------------
# Skill Registry (v0, dev-safe)
# -------------------------
def load_skills() -> list:
    try:
        import json
        if not SKILLS_PATH.exists():
            return []
        data = json.loads(SKILLS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []

def get_skill_by_id(skill_id: str):
    for sk in load_skills():
        if isinstance(sk, dict) and sk.get("skill_id") == skill_id:
            return sk
    return None

# -------------------------
# Decision 2: Rule-based skill demonstration assessment (v0)
# -------------------------
@app.post("/assess/skill")
def assess_skill(payload: dict, request: Request = None):
    """
    Decision 2 (rule-based v0):
      - retrieve Top-K evidence by BM25 (Decision 1)
      - rule-based decision: demonstrated / mentioned / not_enough_information
      - optional store into skill_assessments (JSONB)
    """
    import re as _re
    import json as _json
    import uuid as _uuid
    from datetime import datetime, timezone as _tz

    skill_id = (payload.get("skill_id") or "").strip()
    doc_id = (payload.get("doc_id") or "").strip()

    # Week10 strict: block analysis without granted consent
    require_consent_granted(doc_id)

    # Week11 RBAC: only enforce when called from HTTP (request present)
    if request is not None:
        user = get_current_user(request)
        require_doc_access(engine, user, doc_id)
    if not skill_id:
        raise HTTPException(status_code=400, detail="Missing skill_id")
    if not doc_id:
        raise HTTPException(status_code=400, detail="Missing doc_id")

    k = int(payload.get("k") or 10)
    k = max(1, min(k, 50))
    store = bool(payload.get("store") if payload.get("store") is not None else True)

    sk = get_skill_by_id(skill_id)
    if not sk:
        raise HTTPException(status_code=404, detail="Skill not found")

    canonical = sk.get("canonical_name") or ""
    definition = sk.get("definition") or ""
    aliases = sk.get("aliases") or []
    alias_text = " ".join([a for a in aliases if isinstance(a, str)])
    generated_query = f"{canonical}. {definition} Aliases: {alias_text}".strip()

    # Decision 1 retrieval
    retrieval = search_evidence({
        "query": generated_query,
        "doc_id": doc_id,
        "k": k,
        "include_breakdown": False
    })
    evidence = retrieval.get("items") or []

    def tok(text: str):
        text = (text or "").lower()
        toks = _re.findall(r"[a-z0-9]+", text)
        stop = {
            "the","a","an","and","or","to","of","in","on","for","with","is","are","was","were","be","as","by",
            "it","this","that","from","at","we","you","they","he","she","i","me","my","our","your","their"
        }
        toks = [t for t in toks if t not in stop]
        toks = [t for t in toks if len(t) >= 2]
        return toks

    key_terms = set(tok(canonical + " " + alias_text))

    best = None
    matched_terms = []

    if evidence:
        best_distinct = 0
        best_matched = []
        with engine.connect() as conn:
            for ev in evidence:
                chunk_id = ev.get("chunk_id")
                if not chunk_id:
                    continue
                row = conn.execute(
                    text("SELECT chunk_text FROM chunks WHERE chunk_id = (:chunk_id)::uuid"),
                    {"chunk_id": chunk_id},
                ).mappings().first()
                chunk_text = (row.get("chunk_text") if row else "") or ""
                chunk_tokens = set(tok(chunk_text))
                matched = sorted(list(chunk_tokens.intersection(key_terms)))
                distinct = len(matched)

                if (distinct > best_distinct) or (distinct == best_distinct and float(ev.get("score", 0) or 0) > float(best.get("score", 0) or 0) if best else True):
                    best_distinct = distinct
                    best_matched = matched
                    best = ev

        matched_terms = best_matched

    # Decision rule (v0)
    if best and len(matched_terms) >= 2 and float(best.get("score", 0) or 0) >= 2.5:
        decision = "demonstrated"
    elif best and len(matched_terms) >= 1:
        decision = "mentioned"
    else:
        decision = "not_enough_information"

    if store:
        ddl = """
        CREATE TABLE IF NOT EXISTS skill_assessments (
            assessment_id UUID PRIMARY KEY,
            doc_id UUID NOT NULL,
            skill_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            evidence JSONB NOT NULL,
            decision_meta JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_skill_assessments_doc ON skill_assessments(doc_id);
        CREATE INDEX IF NOT EXISTS idx_skill_assessments_skill ON skill_assessments(skill_id);
        """
        with engine.begin() as conn:
            conn.execute(text(ddl))

            assessment_id = str(_uuid.uuid4())
            created_at = datetime.now(_tz.utc).isoformat()

            decision_meta = {
                "type": "rule_v0",
                "rule": {
                    "key_terms_source": "canonical_name + aliases",
                    "demonstrated": {"min_distinct_terms": 2, "min_retrieval_score": 2.5},
                    "mentioned": {"min_distinct_terms": 1},
                },
                "generated_query": generated_query,
                "retrieval_scoring": retrieval.get("scoring"),
                "retrieval_N": retrieval.get("N"),
                "retrieval_avgdl": retrieval.get("avgdl"),
                "best_chunk_id": (best.get("chunk_id") if best else None),
                "matched_terms": matched_terms,
            }

            # IMPORTANT: default=str makes UUID/datetime JSON-serializable safely
            evidence_json = _json.dumps(evidence, default=str)
            meta_json = _json.dumps(decision_meta, default=str)

            conn.execute(
                text("""
                    INSERT INTO skill_assessments (assessment_id, doc_id, skill_id, decision, evidence, decision_meta, created_at)
                    VALUES ((:assessment_id)::uuid, (:doc_id)::uuid, :skill_id, :decision, (:evidence)::jsonb, (:decision_meta)::jsonb, :created_at)
                """),
                {
                    "assessment_id": assessment_id,
                    "doc_id": doc_id,
                    "skill_id": skill_id,
                    "decision": decision,
                    "evidence": evidence_json,
                    "decision_meta": meta_json,
                    "created_at": created_at,
                },
            )

    return {
        "skill_id": skill_id,
        "doc_id": doc_id,
        "decision": decision,
        "matched_terms": matched_terms,
        "best_evidence": best,
        "evidence": evidence,
        "decision_meta": {
            "type": "rule_v0",
            "generated_query": generated_query,
            "rule_summary": "demonstrated if >=2 key terms in best chunk and score>=2.5; mentioned if >=1; else refuse",
        },
    }

@app.get("/documents/{doc_id}/assessments")
def list_assessments(doc_id: str, limit: int = 20):
    limit = max(1, min(limit, 100))

    with engine.connect() as conn:
        # Return newest first
        rows = conn.execute(
            text("""
                SELECT assessment_id, doc_id, skill_id, decision, decision_meta, created_at
                FROM skill_assessments
                WHERE doc_id = (:doc_id)::uuid
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"doc_id": doc_id, "limit": limit},
        ).mappings().all()

    return {"items": [dict(r) for r in rows]}

# -------------------------
# Decision 3: Rule-based proficiency (v0)
# -------------------------
@app.post("/assess/proficiency")
def assess_proficiency(payload: dict, request: Request):
    """
    Decision 3 (rule_v1):
      - reuses Decision 2 outputs (decision + matched_terms + evidence list)
      - uses coverage across evidence, not just one high score
    """
    import uuid as _uuid
    import json as _json
    import re as _re
    from datetime import datetime, timezone as _tz

    skill_id = (payload.get("skill_id") or "").strip()
    doc_id = (payload.get("doc_id") or "").strip()

    # Week10 strict: block analysis without granted consent
    require_consent_granted(doc_id)

    # Week11 RBAC: only enforce when called from HTTP (request present)
    if request is not None:
        user = get_current_user(request)
        require_doc_access(engine, user, doc_id)
    if not skill_id:
        raise HTTPException(status_code=400, detail="Missing skill_id")
    if not doc_id:
        raise HTTPException(status_code=400, detail="Missing doc_id")

    k = int(payload.get("k") or 10)
    k = max(1, min(k, 50))
    store = bool(payload.get("store") if payload.get("store") is not None else True)

    # Run Decision 2 once (no store) to avoid double writes
    d2 = assess_skill({"skill_id": skill_id, "doc_id": doc_id, "k": k, "store": False})
    decision2 = d2.get("decision")
    matched_terms = d2.get("matched_terms") or []
    evidence = d2.get("evidence") or []
    best = d2.get("best_evidence")
    best_score = float(best.get("score", 0) or 0) if best else 0.0
    distinct_terms = len(matched_terms)

    # Tokenize helper
    def tok(text: str):
        text = (text or "").lower()
        toks = _re.findall(r"[a-z0-9]+", text)
        stop = {
            "the","a","an","and","or","to","of","in","on","for","with","is","are","was","were","be","as","by",
            "it","this","that","from","at","we","you","they","he","she","i","me","my","our","your","their"
        }
        toks = [t for t in toks if t not in stop]
        toks = [t for t in toks if len(t) >= 2]
        return toks

    sk = get_skill_by_id(skill_id)
    if not sk:
        raise HTTPException(status_code=404, detail="Skill not found")

    canonical = sk.get("canonical_name") or ""
    aliases = sk.get("aliases") or []
    alias_text = " ".join([a for a in aliases if isinstance(a, str)])
    key_terms = set(tok(canonical + " " + alias_text))

    # coverage_count: how many evidence chunks contain >=1 key term
    coverage_count = 0
    with engine.connect() as conn:
        for ev in evidence:
            cid = ev.get("chunk_id")
            if not cid:
                continue
            row = conn.execute(
                text("SELECT chunk_text FROM chunks WHERE chunk_id = (:cid)::uuid"),
                {"cid": cid},
            ).mappings().first()
            chunk_text = (row.get("chunk_text") if row else "") or ""
            chunk_tokens = set(tok(chunk_text))
            if chunk_tokens.intersection(key_terms):
                coverage_count += 1

    # Rule v1
    if decision2 == "not_enough_information":
        level, label = 0, "novice"
        rationale = "Not enough evidence to support a proficiency claim."
    elif decision2 == "mentioned":
        level, label = 1, "developing"
        rationale = "Evidence mentions the skill but does not strongly demonstrate it."
    else:
        # demonstrated
        if coverage_count >= 2 and distinct_terms >= 2:
            level, label = 3, "advanced"
            rationale = "Strong evidence across multiple chunks with multiple key terms."
        else:
            level, label = 2, "proficient"
            rationale = "Evidence demonstrates the skill, but coverage or term diversity is limited."

    result = {
        "skill_id": skill_id,
        "doc_id": doc_id,
        "level": level,
        "label": label,
        "rationale": rationale,
        "best_evidence": best,
        "signals": {
            "decision2": decision2,
            "distinct_key_terms": distinct_terms,
            "coverage_count": coverage_count,
            "best_retrieval_score": best_score,
            "matched_terms": matched_terms,
        },
        "meta": {
            "type": "rule_v1",
            "level_rule": {
                "not_enough_information": 0,
                "mentioned": 1,
                "demonstrated": {"coverage>=2 AND terms>=2": 3, "else": 2},
            },
        },
    }

    if store:
        ddl = """
        CREATE TABLE IF NOT EXISTS skill_proficiency (
            prof_id UUID PRIMARY KEY,
            doc_id UUID NOT NULL,
            skill_id TEXT NOT NULL,
            level INTEGER NOT NULL,
            label TEXT NOT NULL,
            rationale TEXT NOT NULL,
            best_evidence JSONB NOT NULL,
            signals JSONB NOT NULL,
            meta JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_skill_prof_doc ON skill_proficiency(doc_id);
        CREATE INDEX IF NOT EXISTS idx_skill_prof_skill ON skill_proficiency(skill_id);
        """
        with engine.begin() as conn:
            conn.execute(text(ddl))
            conn.execute(
                text("""
                    INSERT INTO skill_proficiency
                    (prof_id, doc_id, skill_id, level, label, rationale, best_evidence, signals, meta, created_at)
                    VALUES
                    ((:prof_id)::uuid, (:doc_id)::uuid, :skill_id, :level, :label, :rationale,
                     (:best_evidence)::jsonb, (:signals)::jsonb, (:meta)::jsonb, :created_at)
                """),
                {
                    "prof_id": str(_uuid.uuid4()),
                    "doc_id": doc_id,
                    "skill_id": skill_id,
                    "level": level,
                    "label": label,
                    "rationale": rationale,
                    "best_evidence": _json.dumps(best or {}, default=str),
                    "signals": _json.dumps(result["signals"], default=str),
                    "meta": _json.dumps(result["meta"], default=str),
                    "created_at": datetime.now(_tz.utc).isoformat(),
                },
            )

    return result

@app.get("/documents/{doc_id}/proficiency")
def list_proficiency(doc_id: str, limit: int = 20):
    limit = max(1, min(limit, 100))
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT prof_id, doc_id, skill_id, level, label, rationale, created_at
                FROM skill_proficiency
                WHERE doc_id = (:doc_id)::uuid
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"doc_id": doc_id, "limit": limit},
        ).mappings().all()
    return {"items": [dict(r) for r in rows]}

# -------------------------
# Roles + Actions (Decision 4/5) - v0
# -------------------------
from functools import lru_cache
import json as _json
from pathlib import Path as _Path

ROLES_PATH = _Path(__file__).resolve().parent.parent / "data" / "roles.json"
ACTIONS_PATH = _Path(__file__).resolve().parent.parent / "data" / "action_templates.json"

@lru_cache(maxsize=1)
def load_roles() -> list:
    try:
        if not ROLES_PATH.exists():
            return []
        data = _json.loads(ROLES_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []

def get_role_by_id(role_id: str):
    for r in load_roles():
        if isinstance(r, dict) and r.get("role_id") == role_id:
            return r
    return None

@lru_cache(maxsize=1)
def load_action_templates() -> list:
    try:
        if not ACTIONS_PATH.exists():
            return []
        data = _json.loads(ACTIONS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []

def find_action_template(skill_id: str, gap_type: str):
    for t in load_action_templates():
        if t.get("skill_id") == skill_id and t.get("gap_type") == gap_type:
            return t
    return None

@app.get("/roles")
def list_roles():
    return {"items": load_roles()}

@app.get("/roles/{role_id}")
def get_role(role_id: str):
    r = get_role_by_id(role_id)
    if not r:
        raise HTTPException(status_code=404, detail="Role not found")
    return r

@app.post("/assess/role_readiness")
def assess_role_readiness(payload: dict, request: Request = None):
    """
    Decision 4 (dev-safe): returns JSON error detail on failure.
    """
    try:
        import uuid as _uuid

        doc_id = (payload.get("doc_id") or "").strip()
        role_id = (payload.get("role_id") or "").strip()

        if not doc_id:
            raise HTTPException(status_code=400, detail="Missing doc_id")
        if not role_id:
            raise HTTPException(status_code=400, detail="Missing role_id")

        try:
            _uuid.UUID(doc_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid doc_id format")

        require_consent_granted(doc_id)

        if request is not None:
            user = get_current_user(request)
            require_doc_access(engine, user, doc_id)

        role = get_role_by_id(role_id)
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")

        items = []
        counts = {"meet": 0, "missing_proof": 0, "needs_strengthening": 0}

        for req_item in role.get("skills_required", []):
            skill_id = req_item.get("skill_id")
            target = int(req_item.get("target_level") or 0)
            required = bool(req_item.get("required") if req_item.get("required") is not None else True)

            with engine.connect() as conn:
                row = conn.execute(
                    text("""
                        SELECT level, label, created_at
                        FROM skill_proficiency
                        WHERE doc_id = (:doc_id)::uuid AND skill_id = :skill_id
                        ORDER BY created_at DESC
                        LIMIT 1
                    """),
                    {"doc_id": doc_id, "skill_id": skill_id},
                ).mappings().first()

            if row:
                observed_level = int(row["level"])
                observed_label = row["label"]
                source = "stored_proficiency"
            else:
                prof = assess_proficiency({"skill_id": skill_id, "doc_id": doc_id, "k": 10, "store": False}, request=None)
                observed_level = int(prof["level"])
                observed_label = prof["label"]
                source = "computed_proficiency"

            if observed_level == 0:
                status = "missing_proof"
            elif observed_level < target:
                status = "needs_strengthening"
            else:
                status = "meet"

            counts[status] += 1
            items.append({
                "skill_id": skill_id,
                "required": required,
                "target_level": target,
                "observed_level": observed_level,
                "observed_label": observed_label,
                "status": status,
                "source": source,
            })

        return {
            "doc_id": doc_id,
            "role_id": role_id,
            "role_title": role.get("role_title"),
            "summary": counts,
            "items": items,
            "meta": {"type": "rule_v0"},
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"role_readiness failed: {type(e).__name__}: {e}")

@app.post("/actions/recommend")
def recommend_actions(payload: dict, request: Request = None):
    """
    Decision 5 (dev-safe): returns JSON error detail on failure.
    """
    try:
        import uuid as _uuid

        doc_id = (payload.get("doc_id") or "").strip()
        role_id = (payload.get("role_id") or "").strip()

        if not doc_id:
            raise HTTPException(status_code=400, detail="Missing doc_id")
        if not role_id:
            raise HTTPException(status_code=400, detail="Missing role_id")

        try:
            _uuid.UUID(doc_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid doc_id format")

        require_consent_granted(doc_id)

        if request is not None:
            user = get_current_user(request)
            require_doc_access(engine, user, doc_id)

        readiness = assess_role_readiness({"doc_id": doc_id, "role_id": role_id, "store": False}, request=None)

        cards = []
        for it in readiness.get("items") or []:
            status = it.get("status")
            if status == "meet":
                continue
            gap_type = "missing_proof" if status == "missing_proof" else "needs_strengthening"
            tmpl = find_action_template(it["skill_id"], gap_type)

            card = {
                "skill_id": it["skill_id"],
                "gap_type": gap_type,
                "title": (tmpl["title"] if tmpl else f"Action for {it['skill_id']}"),
                "why_this_card": f"Status={status}. Observed {it['observed_level']} ({it['observed_label']}) vs target {it['target_level']}.",
                "based_on": it,
                "what_to_do": (tmpl["what_to_do"] if tmpl else "Add evidence for this skill."),
                "artifact": (tmpl["artifact"] if tmpl else "Short text artifact"),
                "how_verified": (tmpl["how_verified"] if tmpl else "Instructor can locate the cited paragraph."),
            }
            cards.append(card)

        return {
            "doc_id": doc_id,
            "role_id": role_id,
            "role_title": readiness.get("role_title"),
            "summary": readiness.get("summary"),
            "action_cards": cards,
            "meta": {"type": "template_v0"},
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"actions failed: {type(e).__name__}: {e}")

@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    """
    Safe audit middleware:
      - audits selected JSON POST endpoints (request payload only)
      - NEVER consumes response body (prevents empty responses)
      - best-effort: any audit failure is swallowed
    """
    import time as _time
    import json as _json

    path = request.url.path
    method = request.method.upper()

    ct = (request.headers.get("content-type") or "").lower()
    should_audit = (method == "POST" and path in globals().get("AUDIT_PATHS", {}) and "application/json" in ct)

    req_payload = {}
    doc_id_text = None
    start = _time.time()

    if should_audit:
        try:
            body = await request.body()
            req_payload = _json.loads(body.decode("utf-8")) if body else {}
            if isinstance(req_payload, dict):
                doc_id_text = req_payload.get("doc_id")
        except Exception:
            req_payload = {"_audit_parse_error": True}

    try:
        response = await call_next(request)
        status_code = getattr(response, "status_code", 200)
        return response
    finally:
        if should_audit:
            try:
                elapsed_ms = int((_time.time() - start) * 1000)
                audit_payload = {"request": req_payload, "_elapsed_ms": elapsed_ms}
                audit_log(
                    event_type=globals().get("AUDIT_PATHS", {}).get(path, "AUDIT_UNKNOWN"),
                    path=path,
                    method=method,
                    doc_id_text=doc_id_text,
                    status_code=status_code,
                    payload_obj=audit_payload,
                )
            except Exception:
                pass

@app.get("/audit")
def list_audit(doc_id: str | None = None, limit: int = 20):
    limit = max(1, min(limit, 200))
    where = ""
    params = {"limit": limit}
    if doc_id:
        where = "WHERE doc_id_text = :doc_id"
        params["doc_id"] = doc_id

    with engine.connect() as conn:
        rows = conn.execute(
            text(f'''
                SELECT audit_id, event_type, path, method, doc_id_text, status_code, created_at, payload
                FROM audit_logs
                {where}
                ORDER BY created_at DESC
                LIMIT :limit
            '''),
            params,
        ).mappings().all()
    return {"items": [dict(r) for r in rows]}

@app.get("/changes")
def changes(doc_id: str | None = None, limit: int = 20):
    return {"items": list_changes(engine, doc_id, limit)}


# -------------------------
# Week9: Parsers (DOCX/PDF) + chunking v1
# -------------------------
def parse_docx_to_chunks(docx_path: str):
    """Return list of chunks with (section_path, page_start, page_end, chunk_text, snippet, char_start, char_end)."""
    from docx import Document

    doc = Document(docx_path)

    chunks = []
    # Track section path using heading styles
    current_section = []
    full_text_acc = ""  # to compute char offsets for docx (not perfect but consistent)

    def add_chunk(text: str, section_path: str | None):
        nonlocal full_text_acc
        text_norm = text.strip()
        if not text_norm:
            return
        start = len(full_text_acc)
        full_text_acc += text_norm + "\n\n"
        end = len(full_text_acc)
        chunks.append({
            "section_path": section_path,
            "page_start": None,
            "page_end": None,
            "char_start": start,
            "char_end": end,
            "chunk_text": text_norm,
        })

    # Paragraphs with heading detection
    for para in doc.paragraphs:
        style = (para.style.name or "") if para.style else ""
        txt = para.text or ""
        if not txt.strip():
            continue

        if style.startswith("Heading"):
            # derive heading level number if possible
            level = 1
            try:
                level = int(style.split()[-1])
            except Exception:
                level = 1
            title = txt.strip()
            # update current_section stack
            current_section = current_section[: max(0, level - 1)]
            current_section.append(title)
            # also store heading itself as a chunk (helps retrieval)
            add_chunk(title, " > ".join(current_section))
        else:
            add_chunk(txt, " > ".join(current_section) if current_section else None)

    # Tables
    for t_i, table in enumerate(doc.tables):
        rows_text = []
        for row in table.rows:
            cells = [c.text.strip().replace("\n", " ") for c in row.cells]
            rows_text.append(" | ".join([c for c in cells if c]))
        table_txt = "\n".join([r for r in rows_text if r.strip()])
        if table_txt.strip():
            add_chunk(f"[TABLE {t_i}]\n" + table_txt, " > ".join(current_section) if current_section else None)

    return chunks


def parse_pdf_to_chunks(pdf_path: str):
    """Return list of page chunks with (page_start/page_end, chunk_text). section_path None."""
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    chunks = []
    full_text_acc = ""

    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        txt = txt.strip()
        if not txt:
            # still record empty page? skip for now
            continue
        start = len(full_text_acc)
        full_text_acc += txt + "\n\n"
        end = len(full_text_acc)
        chunks.append({
            "section_path": None,
            "page_start": i + 1,
            "page_end": i + 1,
            "char_start": start,
            "char_end": end,
            "chunk_text": txt,
        })
    return chunks
# -------------------------
# Week10: Strict Consent (v1) - block upload + block analysis without consent
# -------------------------
import uuid as _uuid
import json as _json
from datetime import datetime as _dt, timezone as _tz

def ensure_consents_table():
    ddl = """
    CREATE TABLE IF NOT EXISTS consents (
        consent_id UUID PRIMARY KEY,
        doc_id UUID NOT NULL UNIQUE,
        subject_id TEXT NOT NULL,
        scope TEXT NOT NULL,
        status TEXT NOT NULL,          -- granted / revoked
        upload_token UUID NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        revoked_at TIMESTAMPTZ,
        revoke_reason TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_consents_doc ON consents(doc_id);
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))

def require_consent_granted(doc_id: str):
    ensure_consents_table()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT status
                FROM consents
                WHERE doc_id = (:doc_id)::uuid
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"doc_id": doc_id},
        ).mappings().first()

    if not row or row["status"] != "granted":
        raise HTTPException(status_code=403, detail="Consent required (grant consent before upload/analysis).")

def require_upload_token(doc_id: str, upload_token: str):
    ensure_consents_table()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT status, upload_token
                FROM consents
                WHERE doc_id = (:doc_id)::uuid
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"doc_id": doc_id},
        ).mappings().first()

    if not row or row["status"] != "granted":
        raise HTTPException(status_code=403, detail="Consent required (grant consent before upload).")

    if str(row["upload_token"]) != str(upload_token):
        raise HTTPException(status_code=403, detail="Invalid upload_token for this doc_id.")

@app.post("/consent/start")
def consent_start(payload: dict, request: Request):
    """
    Week11 strict: subject_id comes from request headers (get_current_user).
    Payload only needs: {"scope": "analysis"} (optional).
    Returns doc_id + upload_token.
    """
    ensure_consents_table()

    user = get_current_user(request)
    subject_id = user["subject_id"]
    scope = (payload.get("scope") or "analysis").strip()
    if not scope:
        raise HTTPException(status_code=400, detail="Missing scope")

    doc_id = str(_uuid.uuid4())
    upload_token = str(_uuid.uuid4())

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO consents (consent_id, doc_id, subject_id, scope, status, upload_token, created_at)
                VALUES ((:cid)::uuid, (:doc_id)::uuid, :subject_id, :scope, 'granted', (:upload_token)::uuid, :created_at)
            """),
            {
                "cid": str(_uuid.uuid4()),
                "doc_id": doc_id,
                "subject_id": subject_id,
                "scope": scope,
                "upload_token": upload_token,
                "created_at": _dt.now(_tz.utc).isoformat(),
            },
        )

    return {"doc_id": doc_id, "upload_token": upload_token, "subject_id": subject_id, "scope": scope, "status": "granted"}

@app.get("/consent/status")
def consent_status(doc_id: str):
    ensure_consents_table()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT subject_id, scope, status, created_at, revoked_at, revoke_reason
                FROM consents
                WHERE doc_id = (:doc_id)::uuid
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"doc_id": doc_id},
        ).mappings().first()

    if not row:
        return {"doc_id": doc_id, "status": "none"}
    return {"doc_id": doc_id, **dict(row)}

def purge_document(doc_id: str):
    # 1) find stored_path (if exists)
    stored_path = None
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT stored_path FROM documents WHERE doc_id = (:doc_id)::uuid"),
            {"doc_id": doc_id},
        ).mappings().first()
        if row:
            stored_path = row["stored_path"]

    # 2) delete from DB (documents has FK cascade for chunks)
    with engine.begin() as conn:
        # delete dependent tables keyed by doc_id
        conn.execute(text("DELETE FROM skill_assessments WHERE doc_id = (:doc_id)::uuid"), {"doc_id": doc_id})
        conn.execute(text("DELETE FROM skill_proficiency WHERE doc_id = (:doc_id)::uuid"), {"doc_id": doc_id})
        conn.execute(text("DELETE FROM role_readiness WHERE doc_id = (:doc_id)::uuid"), {"doc_id": doc_id})

        # audit/change logs use doc_id_text
        conn.execute(text("DELETE FROM audit_logs WHERE doc_id_text = :doc_id"), {"doc_id": doc_id})
        conn.execute(text("DELETE FROM change_logs WHERE doc_id_text = :doc_id"), {"doc_id": doc_id})

        # documents (cascades chunks)
        conn.execute(text("DELETE FROM documents WHERE doc_id = (:doc_id)::uuid"), {"doc_id": doc_id})

    # 3) delete file on disk
    if stored_path:
        try:
            _Path(stored_path).unlink(missing_ok=True)
        except Exception:
            pass

    # Week10: also delete vectors for this doc_id (best-effort)
    try:
        delete_by_doc_id(get_client(), doc_id)
    except Exception:
        pass

@app.post("/consent/revoke")
def consent_revoke(payload: dict, request: Request):
    """
    Week11 strict:
      - subject_id/role come from request headers (get_current_user)
      - admin can revoke any doc
      - student can revoke only own doc
      - revoke triggers physical delete (purge_document)
    """
    ensure_consents_table()

    user = get_current_user(request)
    subject_id = user["subject_id"]
    role = user["role"]

    doc_id = (payload.get("doc_id") or "").strip()
    upload_token = (payload.get("upload_token") or "").strip()
    reason = (payload.get("reason") or "").strip()

    if not doc_id:
        raise HTTPException(status_code=400, detail="Missing doc_id")
    if not upload_token:
        raise HTTPException(status_code=400, detail="Missing upload_token")

    # Must be granted + token match
    require_upload_token(doc_id, upload_token)

    # Owner/admin check
    if role != "admin":
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT subject_id FROM documents WHERE doc_id = (:doc_id)::uuid"),
                {"doc_id": doc_id},
            ).mappings().first()
        if row and row.get("subject_id") != subject_id:
            raise HTTPException(status_code=403, detail="Forbidden: not owner")

    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE consents
                SET status='revoked', revoked_at=:revoked_at, revoke_reason=:reason
                WHERE doc_id = (:doc_id)::uuid
            """),
            {
                "doc_id": doc_id,
                "revoked_at": _dt.now(_tz.utc).isoformat(),
                "reason": reason,
            },
        )

    purge_document(doc_id)
    return {"doc_id": doc_id, "status": "revoked", "deleted": True}

@app.get("/whoami")
def whoami(request: Request):
    user = get_current_user(request)
    return {"subject_id": user["subject_id"], "role": user["role"]}

from qdrant_client.http import models as qm
from app.vector_store import get_client, ensure_collection, upsert_points, search as q_search, delete_by_doc_id
from app.embeddings import embed_texts, emb_dim, MODEL_NAME

@app.post("/embeddings/reindex")
def embeddings_reindex(request: Request):
    """
    Week10: index all chunks for documents with consent status='granted'
    into Qdrant, with payload including created_at_ts for time filtering.
    staff/admin only.
    """
    from datetime import datetime, timezone

    user = get_current_user(request)
    if user["role"] not in {"staff", "admin"}:
        raise HTTPException(status_code=403, detail="staff/admin only")

    client = get_client()
    ensure_collection(client, emb_dim())

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
              c.chunk_id::text as chunk_id,
              c.doc_id::text as doc_id,
              c.idx,
              c.snippet,
              c.chunk_text,
              c.section_path,
              c.page_start,
              c.page_end,
              d.doc_type,
              d.subject_id,
              d.created_at
            FROM chunks c
            JOIN documents d ON d.doc_id = c.doc_id
            JOIN consents  x ON x.doc_id = d.doc_id AND x.status = 'granted'
            ORDER BY d.created_at DESC, c.idx ASC
        """)).mappings().all()

    if not rows:
        return {"ok": True, "count": 0, "model": MODEL_NAME, "note": "No granted documents to index."}

    texts = [r["chunk_text"] for r in rows]
    vecs = embed_texts(texts)

    points = []
    for r, v in zip(rows, vecs):
        # created_at is timestamptz from DB; convert to epoch seconds
        created_at_str = str(r["created_at"])
        try:
            dt = datetime.fromisoformat(created_at_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            created_at_ts = int(dt.timestamp())
        except Exception:
            created_at_ts = None

        payload = {
            "chunk_id": r["chunk_id"],
            "doc_id": r["doc_id"],
            "idx": int(r["idx"]),
            "snippet": r["snippet"],
            "section_path": r["section_path"],
            "page_start": r["page_start"],
            "page_end": r["page_end"],
            "doc_type": r["doc_type"],
            "subject_id": r["subject_id"],
            "created_at": created_at_str,
            "created_at_ts": created_at_ts,
        }
        points.append(qm.PointStruct(id=r["chunk_id"], vector=v, payload=payload))

    upsert_points(client, points)
    return {"ok": True, "count": len(points), "model": MODEL_NAME}

@app.post("/embeddings/reindex")
def embeddings_reindex(request: Request):
    """
    Staff/admin only: index all chunks for documents with consent status='granted'.
    """
    user = get_current_user(request)
    if user["role"] not in {"staff", "admin"}:
        raise HTTPException(status_code=403, detail="staff/admin only")

    client = get_client()
    ensure_collection(client, emb_dim())

    # Only index documents that are currently granted in consents (strict mode)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
              c.chunk_id::text as chunk_id,
              c.doc_id::text as doc_id,
              c.idx,
              c.snippet,
              c.chunk_text,
              c.section_path,
              c.page_start,
              c.page_end,
              d.doc_type,
              d.subject_id,
              d.created_at
            FROM chunks c
            JOIN documents d ON d.doc_id = c.doc_id
            JOIN consents  x ON x.doc_id = d.doc_id AND x.status = 'granted'
            ORDER BY d.created_at DESC, c.idx ASC
        """)).mappings().all()

    if not rows:
        return {"ok": True, "count": 0, "model": MODEL_NAME, "note": "No granted documents to index."}

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
            "doc_type": r["doc_type"],
            "subject_id": r["subject_id"],
            "created_at": str(r["created_at"]),
        }
        points.append(qm.PointStruct(id=r["chunk_id"], vector=v, payload=payload))

    upsert_points(client, points)
    return {"ok": True, "count": len(points), "model": MODEL_NAME}


@app.post("/search/evidence_vector")
def search_evidence_vector(payload: dict, request: Request):
    """
    Week10 Decision 1: vector retrieval (Qdrant).

    Input:
      - skill_id OR query_text
      - k (default 10)
      - optional filters:
          doc_id (strict: requires granted consent + RBAC doc access)
          doc_type
          time_from (epoch seconds, inclusive)
          time_to   (epoch seconds, inclusive)

    RBAC:
      - student can only see own subject_id (global filter)
      - if doc_id is provided: require_doc_access(engine, user, doc_id)
    """
    user = get_current_user(request)

    top_k = int(payload.get("k") or 10)
    top_k = max(1, min(top_k, 50))

    doc_id = payload.get("doc_id")
    doc_type = payload.get("doc_type")
    skill_id = payload.get("skill_id")
    query_text = (payload.get("query_text") or "").strip()

    time_from = payload.get("time_from")  # epoch seconds
    time_to = payload.get("time_to")      # epoch seconds

    if time_from is not None and not isinstance(time_from, int):
        raise HTTPException(status_code=400, detail="time_from must be epoch seconds (int)")
    if time_to is not None and not isinstance(time_to, int):
        raise HTTPException(status_code=400, detail="time_to must be epoch seconds (int)")

    if skill_id:
        sk = get_skill_by_id(skill_id)
        if not sk:
            raise HTTPException(status_code=404, detail="Skill not found")
        canonical = sk.get("canonical_name") or ""
        definition = sk.get("definition") or ""
        aliases = " ".join(sk.get("aliases") or [])
        query_text = f"{canonical}. {definition} Aliases: {aliases}".strip()

    if not query_text:
        raise HTTPException(status_code=400, detail="Missing query_text or skill_id")

    # strict: doc scope requires granted consent + RBAC
    if doc_id:
        require_consent_granted(doc_id)
        require_doc_access(engine, user, doc_id)

    client = get_client()
    ensure_collection(client, emb_dim())
    qvec = embed_texts([query_text])[0]

    must = []
    # RBAC: student sees only own subject_id
    if user["role"] == "student":
        must.append(qm.FieldCondition(key="subject_id", match=qm.MatchValue(value=user["subject_id"])))
    if doc_id:
        must.append(qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id)))
    if doc_type:
        must.append(qm.FieldCondition(key="doc_type", match=qm.MatchValue(value=doc_type)))

    # time range filter (if created_at_ts exists in payload)
    if time_from is not None or time_to is not None:
        rng = qm.Range(gte=time_from, lte=time_to)
        must.append(qm.FieldCondition(key="created_at_ts", range=rng))

    flt = qm.Filter(must=must) if must else None
    hits = q_search(client, qvec, top_k, flt)

    items = []
    for h in hits:
        # qdrant-client hit can be object/dict/pydantic-like
        if isinstance(h, dict):
            score = float(h.get("score", 0.0) or 0.0)
            pld = h.get("payload") or {}
        elif hasattr(h, "payload"):
            score = float(getattr(h, "score", 0.0) or 0.0)
            pld = getattr(h, "payload") or {}
        elif hasattr(h, "dict"):
            d = h.dict()
            score = float(d.get("score", 0.0) or 0.0)
            pld = d.get("payload") or {}
        else:
            score, pld = 0.0, {}

        items.append({
            "chunk_id": pld.get("chunk_id"),
            "doc_id": pld.get("doc_id"),
            "idx": pld.get("idx"),
            "snippet": pld.get("snippet"),
            "section_path": pld.get("section_path"),
            "page_start": pld.get("page_start"),
            "page_end": pld.get("page_end"),
            "score": score,
            "score_meta": {"type": "vector_cosine", "model": MODEL_NAME},
        })

    return {"items": items, "query_text": query_text}

# -------------------------
# Week11: LLM Demonstration (Ollama) + schema + strict refusal (v1)
# -------------------------
from pathlib import Path as _Path2
from app.ollama_client import ollama_generate
from app.schema_validate import load_schema, extract_first_json_obj, validate_or_raise

# repo root = .../skillsight (main.py is in skillsight/backend/app/)
REPO_ROOT = _Path2(__file__).resolve().parents[2]
DEMO_PROMPT_PATH = REPO_ROOT / "packages/prompts/demonstration_v1.txt"
DEMO_SCHEMA_PATH = REPO_ROOT / "packages/schemas/demonstration_v1.json"

DEMO_MODEL = "deepseek-r1:14b"

_demo_prompt = None
_demo_schema = None

def _load_demo_assets():
    global _demo_prompt, _demo_schema
    if _demo_prompt is None:
        _demo_prompt = DEMO_PROMPT_PATH.read_text(encoding="utf-8")
    if _demo_schema is None:
        _demo_schema = load_schema(str(DEMO_SCHEMA_PATH))

@app.post("/ai/demonstration")
def ai_demonstration(payload: dict, request: Request):
    """
    Input:
      {skill_id, doc_id optional, k optional, min_score optional}
    Output:
      JSON schema validated; strict refusal if evidence weak/invalid.
    Dev-safe: returns JSON detail on unexpected failure.
    """
    try:
        _load_demo_assets()

        skill_id = (payload.get("skill_id") or "").strip()
        doc_id = payload.get("doc_id")
        k = int(payload.get("k") or 5)
        k = max(1, min(k, 20))
        min_score = float(payload.get("min_score") or 0.20)

        if not skill_id:
            raise HTTPException(status_code=400, detail="Missing skill_id")

        # retrieve evidence via vector search (Decision 1)
        body = {"skill_id": skill_id, "k": k}
        if doc_id:
            body["doc_id"] = doc_id

        ev = search_evidence_vector(body, request=request)
        evidence_items = ev.get("items") or []

        if not evidence_items:
            return {
                "label": "not_enough_information",
                "evidence_chunk_ids": [],
                "rationale": "No relevant evidence chunks were retrieved for this skill.",
                "refusal_reason": "no_evidence_retrieved"
            }

        top_score = float((evidence_items[0].get("score") or 0.0))
        if top_score < min_score:
            return {
                "label": "not_enough_information",
                "evidence_chunk_ids": [],
                "rationale": "Retrieved evidence is too weak to support a claim.",
                "refusal_reason": "evidence_score_too_low"
            }

        sk = get_skill_by_id(skill_id)
        if not sk:
            raise HTTPException(status_code=404, detail="Skill not found")

        skill_text = f"{sk.get('canonical_name')}. {sk.get('definition')} Aliases: {' '.join(sk.get('aliases') or [])}".strip()

        allowed_ids = [it.get("chunk_id") for it in evidence_items if it.get("chunk_id")]
        evidence_list = []
        for it in evidence_items:
            evidence_list.append({
                "chunk_id": it.get("chunk_id"),
                "snippet": it.get("snippet"),
                "section_path": it.get("section_path"),
                "page_start": it.get("page_start"),
                "page_end": it.get("page_end"),
                "score": it.get("score"),
            })

        prompt = _demo_prompt.replace("{skill_text}", skill_text).replace("{evidence_list}", str(evidence_list))

        last_err = None
        for attempt in (1, 2):
            try:
                raw = ollama_generate(DEMO_MODEL, prompt, temperature=0.0)
            except Exception as e:
                last_err = e
                continue

            try:
                obj = extract_first_json_obj(raw)
                validate_or_raise(obj, _demo_schema)

                label = obj.get("label")
                ids = obj.get("evidence_chunk_ids") or []

                if any(i not in allowed_ids for i in ids):
                    raise ValueError("evidence_chunk_ids contains unknown chunk_id")

                if label in ("demonstrated", "mentioned") and len(ids) == 0:
                    raise ValueError("label requires evidence_chunk_ids")

                if label == "not_enough_information":
                    obj["evidence_chunk_ids"] = []
                    if not obj.get("refusal_reason"):
                        obj["refusal_reason"] = "insufficient_evidence"
                else:
                    obj["refusal_reason"] = None

                return obj

            except Exception as e:
                last_err = e
                continue

        return {
            "label": "not_enough_information",
            "evidence_chunk_ids": [],
            "rationale": "Model output was invalid or not grounded in provided evidence.",
            "refusal_reason": f"schema_or_grounding_failure:{type(last_err).__name__ if last_err else 'unknown'}"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ai_demonstration failed: {type(e).__name__}: {e}")

# -------------------------
# Week12: LLM Proficiency (Rubric v1) + schema + strict grounding
# -------------------------
PROF_PROMPT_PATH = REPO_ROOT / "packages/prompts/proficiency_v1.txt"
PROF_SCHEMA_PATH = REPO_ROOT / "packages/schemas/proficiency_v1.json"

_prof_prompt = None
_prof_schema = None

def _load_prof_assets():
    global _prof_prompt, _prof_schema
    if _prof_prompt is None:
        _prof_prompt = PROF_PROMPT_PATH.read_text(encoding="utf-8")
    if _prof_schema is None:
        _prof_schema = load_schema(str(PROF_SCHEMA_PATH))

@app.post("/ai/proficiency")
def ai_proficiency(payload: dict, request: Request):
    """
    Input:
      {skill_id, doc_id optional, k optional, min_score optional}
    Output:
      {level, label, matched_criteria, evidence_chunk_ids, why}
    """
    _load_prof_assets()

    skill_id = (payload.get("skill_id") or "").strip()
    doc_id = payload.get("doc_id")
    k = int(payload.get("k") or 8)
    k = max(1, min(k, 20))
    min_score = float(payload.get("min_score") or 0.20)

    if not skill_id:
        raise HTTPException(status_code=400, detail="Missing skill_id")

    # vector retrieval
    body = {"skill_id": skill_id, "k": k}
    if doc_id:
        body["doc_id"] = doc_id
    ev = search_evidence_vector(body, request=request)
    evidence_items = ev.get("items") or []

    if not evidence_items:
        return {"level": 0, "label": "novice", "matched_criteria": [], "evidence_chunk_ids": [], "why": "No relevant evidence retrieved."}

    top_score = float((evidence_items[0].get("score") or 0.0))
    if top_score < min_score:
        return {"level": 0, "label": "novice", "matched_criteria": [], "evidence_chunk_ids": [], "why": "Retrieved evidence is too weak to support a proficiency claim."}

    sk = get_skill_by_id(skill_id)
    if not sk:
        raise HTTPException(status_code=404, detail="Skill not found")

    rubric = sk.get("rubric_v1")
    if not rubric:
        raise HTTPException(status_code=400, detail="Skill has no rubric_v1")

    skill_text = f"{sk.get('canonical_name')}. {sk.get('definition')} Aliases: {' '.join(sk.get('aliases') or [])}".strip()

    # Flatten rubric criterion ids
    rubric_levels = rubric.get("levels") or {}
    all_criterion_ids = []
    for lvl, info in rubric_levels.items():
        for c in (info.get("criteria") or []):
            cid = c.get("id")
            if cid:
                all_criterion_ids.append(cid)

    # Allowed chunk_ids from evidence
    allowed_chunk_ids = [it.get("chunk_id") for it in evidence_items if it.get("chunk_id")]

    evidence_list = []
    for it in evidence_items:
        evidence_list.append({
            "chunk_id": it.get("chunk_id"),
            "snippet": it.get("snippet"),
            "section_path": it.get("section_path"),
            "page_start": it.get("page_start"),
            "page_end": it.get("page_end"),
            "score": it.get("score"),
        })

    rubric_text = str(rubric_levels)

    prompt = _prof_prompt.replace("{skill_text}", skill_text).replace("{rubric_text}", rubric_text).replace("{evidence_list}", str(evidence_list))

    last_err = None
    for attempt in (1, 2):
        try:
            raw = ollama_generate(DEMO_MODEL, prompt, temperature=0.0)
            obj = extract_first_json_obj(raw)
            validate_or_raise(obj, _prof_schema)

            level = int(obj.get("level"))
            label = obj.get("label") or ""
            crit = obj.get("matched_criteria") or []
            ids = obj.get("evidence_chunk_ids") or []
            why = obj.get("why") or ""

            # Grounding checks
            if any(c not in all_criterion_ids for c in crit):
                raise ValueError("matched_criteria contains unknown criterion id")
            if any(i not in allowed_chunk_ids for i in ids):
                raise ValueError("evidence_chunk_ids contains unknown chunk_id")

            # Strict rule: if level > 0, must cite at least one chunk and one criterion
            if level > 0:
                if len(ids) == 0 or len(crit) == 0:
                    raise ValueError("level>0 requires evidence_chunk_ids and matched_criteria")
            else:
                obj["evidence_chunk_ids"] = []
                obj["matched_criteria"] = []

            # normalize label by rubric (optional)
            lvl_info = rubric_levels.get(str(level)) or {}
            if lvl_info.get("label"):
                obj["label"] = lvl_info["label"]

            return obj

        except Exception as e:
            last_err = e
            continue

    # fallback
    return {"level": 0, "label": "novice", "matched_criteria": [], "evidence_chunk_ids": [], "why": f"Fallback due to invalid model output: {type(last_err).__name__ if last_err else 'unknown'}."}
