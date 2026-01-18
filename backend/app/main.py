from backend.app.db.session import SessionLocal, engine

from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import HTTPException

def hard_get_role(role_id: str):
    """Hard-wired role lookup to guarantee JSON output."""
    db: Session = SessionLocal()
    try:
        row = db.execute(
            text("SELECT * FROM roles WHERE role_id = :rid LIMIT 1"),
            {"rid": role_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail=f"role_id not found: {role_id}")
        return {"status": "ok", "item": dict(row)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/roles/{{role_id}} failed: {type(e).__name__}: {e}")
    finally:
        db.close()

from sqlalchemy import text, inspect
from fastapi import Depends, FastAPI
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

try:
    from backend.app.db.session import SessionLocal  # type: ignore
except Exception:
    try:
        from backend.app.database import SessionLocal  # type: ignore
    except Exception:
        SessionLocal = None  # type: ignore

from fastapi.middleware.cors import CORSMiddleware

# SkillSight schemas (Week1 Day3)
# NOTE: repo-root/ is expected to be on PYTHONPATH when running uvicorn from repo root.
from schemas.skillsight_models import Skill, Role, EvidencePointer, AuditLog, ConsentRecord  # noqa: F401

app = FastAPI(title="SkillSight API", version="0.1.0")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from fastapi.responses import JSONResponse

@app.get("/__routes")
def __routes():
    return JSONResponse([
        {"path": r.path, "name": r.name, "methods": sorted(list(getattr(r, "methods", []) or []))}
        for r in app.router.routes
    ])

# Local dev CORS (tighten later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/stats")
def stats():
    """
    Lightweight counts for demo smoke-check.
    Defensive: should not fail if table names change.
    """
    from sqlalchemy import text
    from .db.session import SessionLocal

    db = SessionLocal()
    try:
        tables = db.execute(
            text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
        ).fetchall()
        return {
            "status": "ok",
            "public_tables": [r[0] for r in tables],
            "public_table_count": len(tables),
        }
    finally:
        db.close()

@app.get("/schemas/summary")
def schemas_summary():
    """
    Returns the JSONSchema filenames generated under packages/schemas/.
    This is a simple discoverability endpoint for the MVP.
    """
    return {
        "Skill": "packages/schemas/Skill.schema.json",
        "Role": "packages/schemas/Role.schema.json",
        "EvidencePointer": "packages/schemas/EvidencePointer.schema.json",
        "AuditLog": "packages/schemas/AuditLog.schema.json",
        "ConsentRecord": "packages/schemas/ConsentRecord.schema.json",
    }

from backend.app.routers.skills import router as skills_router
from backend.app.routers.roles import router as roles_router

# Week2 MVP routers
app.include_router(skills_router)
app.include_router(roles_router)

@app.get("/skills")
def skills_list(q: str = "", limit: int = 50):
    """
    Demo endpoint. Auto-detect the real skills table name in public schema.
    Supports q search when columns exist.
    """
    insp = inspect(engine)
    tables = set(insp.get_table_names(schema="public"))
    candidates = ["skills", "skill_registry", "skill_proficiency", "skill_assessments", "skill_aliases"]
    table = next((t for t in candidates if t in tables), None)
    if not table:
        return {"status": "error", "detail": "no skills-like table found", "public_tables": sorted(list(tables))}

    cols = [c["name"] for c in insp.get_columns(table, schema="public")]
    limit = max(1, min(int(limit), 500))
    q2 = (q or "").strip()

    db = SessionLocal()
    try:
        # Prefer search on canonical_name/skill_id if present
        has_cn = "canonical_name" in cols
        has_sid = "skill_id" in cols

        if q2 and (has_cn or has_sid):
            parts = []
            if has_cn:
                parts.append("canonical_name ILIKE :q")
            if has_sid:
                parts.append("skill_id ILIKE :q")
            where = " OR ".join(parts)
            sql = text(f"""
                SELECT * FROM {table}
                WHERE ({where})
                ORDER BY 1 NULLS LAST
                LIMIT :limit
            """)
            rows = db.execute(sql, {"q": f"%{q2}%", "limit": limit}).mappings().all()
        else:
            sql = text(f"SELECT * FROM {table} ORDER BY 1 NULLS LAST LIMIT :limit")
            rows = db.execute(sql, {"limit": limit}).mappings().all()

        return {"status": "ok", "table": table, "count": len(rows), "items": [dict(r) for r in rows]}
    finally:
        db.close()
