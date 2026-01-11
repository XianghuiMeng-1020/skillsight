import os
import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
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
async def upload_document(doc_type: str = Form('demo'), file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    allowed_doc_types = {'demo','synthetic','real'}
    if doc_type not in allowed_doc_types:
        raise HTTPException(status_code=400, detail="Invalid doc_type. Use demo/synthetic/real")

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
                    INSERT INTO documents (doc_id, filename, stored_path, created_at, doc_type)
                    VALUES ((:doc_id)::uuid, :filename, :stored_path, :created_at, :doc_type)
                """),
                {
                    "doc_id": doc_id,
                    "filename": file.filename,
                    "stored_path": str(stored_path),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "doc_type": doc_type,
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
                SELECT doc_id, filename, created_at, doc_type
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
def assess_skill(payload: dict):
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
