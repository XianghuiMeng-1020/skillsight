## HARDENED_ROLES_ROUTER
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from backend.app.db.session import SessionLocal, engine

router = APIRouter(tags=["roles"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _roles_columns() -> List[str]:
    insp = inspect(engine)
    tables = set(insp.get_table_names(schema="public"))
    if "roles" not in tables:
        raise RuntimeError(f"'roles' table not found. public tables={sorted(tables)[:50]}")
    return [c["name"] for c in insp.get_columns("roles", schema="public")]

@router.get("/roles")
def list_roles(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        cols = _roles_columns()
        want = []
        for c in ["role_id", "role_title", "description", "source", "created_at", "updated_at"]:
            if c in cols and c not in want:
                want.append(c)
        if not want:
            want = cols[: min(len(cols), 12)]
        sql = text(f"SELECT {', '.join(want)} FROM roles ORDER BY 1 NULLS LAST LIMIT :limit")
        rows = db.execute(sql, {"limit": limit}).mappings().all()
        return {"status": "ok", "count": len(rows), "items": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/roles failed: {type(e).__name__}: {e}")

@router.get("/roles/{role_id}")
def get_role(role_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    try:
        # select only existing cols; never rely on ORM model fields like roles.version
        cols = _roles_columns()
        sql = text("SELECT * FROM roles WHERE role_id = :rid LIMIT 1")
        row = db.execute(sql, {"rid": role_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail=f"role_id not found: {role_id}")
        # filter dict to stable JSON (in case of weird types)
        out = dict(row)
        return {"status": "ok", "item": out}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/roles/{{role_id}} failed: {type(e).__name__}: {e}")

