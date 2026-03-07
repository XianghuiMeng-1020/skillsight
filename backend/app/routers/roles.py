"""Roles router – CRUD operations for role definitions and skill mappings."""
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from backend.app.db.session import engine
from backend.app.security import require_auth

router = APIRouter(tags=["roles"], dependencies=[Depends(require_auth)])

from backend.app.db.deps import get_db

def _roles_columns() -> List[str]:
    insp = inspect(engine)
    tables = set(insp.get_table_names(schema="public"))
    if "roles" not in tables:
        raise RuntimeError(f"'roles' table not found. public tables={sorted(tables)[:50]}")
    return [c["name"] for c in insp.get_columns("roles", schema="public")]

@router.post("/roles/import")
def import_roles(payload: List[Dict[str, Any]], db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Import roles with skills_required into roles and role_skill_requirements."""
    inserted = 0
    for r in payload or []:
        rid = (r.get("role_id") or "").strip()
        if not rid:
            continue
        exists = db.execute(text("SELECT 1 FROM roles WHERE role_id=:rid LIMIT 1"), {"rid": rid}).scalar()
        now = datetime.now(timezone.utc)
        if not exists:
            db.execute(
                text("""
                    INSERT INTO roles (role_id, role_title, description, created_at, updated_at)
                    VALUES (:role_id, :role_title, :description, :created_at, :updated_at)
                """),
                {
                    "role_id": rid,
                    "role_title": r.get("role_title", ""),
                    "description": r.get("description", ""),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            inserted += 1
        skills_req = r.get("skills_required") or []
        for sr in skills_req:
            skill_id = sr.get("skill_id", "").strip()
            if not skill_id:
                continue
            target_level = int(sr.get("target_level", 0))
            required = bool(sr.get("required", True))
            weight = float(sr.get("weight", 1.0))
            req_id = str(uuid.uuid4())
            db.execute(
                text("""
                    INSERT INTO role_skill_requirements (req_id, role_id, skill_id, target_level, required, weight, created_at)
                    VALUES ((:req_id)::uuid, :role_id, :skill_id, :target_level, :required, :weight, :created_at)
                    ON CONFLICT (role_id, skill_id) DO UPDATE SET target_level=EXCLUDED.target_level, required=EXCLUDED.required, weight=EXCLUDED.weight
                """),
                {
                    "req_id": req_id,
                    "role_id": rid,
                    "skill_id": skill_id,
                    "target_level": target_level,
                    "required": required,
                    "weight": weight,
                    "created_at": now,
                },
            )
    db.commit()
    return {"inserted": inserted, "n": len(payload or [])}


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


@router.get("/roles/{role_id}/requirements")
def get_role_requirements(role_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get skill requirements for a role."""
    try:
        # First verify role exists
        role_sql = text("SELECT role_id FROM roles WHERE role_id = :rid LIMIT 1")
        role_row = db.execute(role_sql, {"rid": role_id}).mappings().first()
        if not role_row:
            raise HTTPException(status_code=404, detail=f"role_id not found: {role_id}")
        
        # Get requirements from role_skill_requirements table
        # Using actual column names: target_level, required, weight (no notes, no min_level)
        req_sql = text("""
            SELECT rsr.skill_id, rsr.target_level, rsr.required, rsr.weight,
                   s.canonical_name as skill_name, s.definition as skill_definition
            FROM role_skill_requirements rsr
            LEFT JOIN skills s ON s.skill_id = rsr.skill_id
            WHERE rsr.role_id = :rid
            ORDER BY rsr.weight DESC NULLS LAST, rsr.skill_id ASC
        """)
        rows = db.execute(req_sql, {"rid": role_id}).mappings().all()
        items = [dict(r) for r in rows]
        return {"status": "ok", "role_id": role_id, "count": len(items), "items": items}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/roles/{{role_id}}/requirements failed: {type(e).__name__}: {e}")

