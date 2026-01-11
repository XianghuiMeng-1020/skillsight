import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

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

app = FastAPI(title="SkillSight API", version="0.1")

# CORS for dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    # Minimal table for Week 1
    ddl = """
    CREATE TABLE IF NOT EXISTS documents (
        doc_id UUID PRIMARY KEY,
        filename TEXT NOT NULL,
        stored_path TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    );
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

@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    # Only allow txt for Week1 (simple)
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    # Keep it simple: accept txt only
    lower = file.filename.lower()
    if not lower.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Week1 only supports .txt files")

    doc_id = uuid.uuid4()
    safe_name = f"{doc_id}_{Path(file.filename).name}"
    stored_path = UPLOAD_DIR / safe_name

    try:
        content = await file.read()
        stored_path.write_bytes(content)

        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO documents (doc_id, filename, stored_path, created_at)
                    VALUES (:doc_id, :filename, :stored_path, :created_at)
                """),
                {
                    "doc_id": str(doc_id),
                    "filename": file.filename,
                    "stored_path": str(stored_path),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
    except SQLAlchemyError as e:
        # rollback happens automatically with engine.begin()
        raise HTTPException(status_code=500, detail=f"DB error: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}") from e

    return {"doc_id": str(doc_id), "filename": file.filename}

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

@app.get("/documents/{doc_id}")
def get_document(doc_id: str):
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT doc_id, filename, stored_path, created_at
                FROM documents
                WHERE doc_id = :doc_id
            """),
            {"doc_id": doc_id},
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return dict(row)
