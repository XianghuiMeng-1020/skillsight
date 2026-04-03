import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from backend.app.db.deps import get_db
from backend.app.db.session import engine
from backend.app.security import Identity, require_auth

router = APIRouter(prefix="/proficiency", tags=["proficiency"])


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


@router.get("/user/{user_id}/skill/{skill_id}")
def get_user_skill_proficiency(
    user_id: str,
    skill_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """Get proficiency for a specific user and skill combination. Users may only query their own; admin may query any."""
    if ident.subject_id != user_id and ident.role != "admin":
        raise HTTPException(status_code=403, detail="Not allowed to view another user's proficiency")
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names(schema="public"))
        if "skill_proficiency" not in tables:
            return {"user_id": user_id, "skill_id": skill_id, "level": None, "message": "No proficiency data available"}
        
        # Try to find proficiency from documents uploaded by this user
        sql = text("""
            SELECT sp.prof_id, sp.doc_id, sp.skill_id, sp.level, sp.label, sp.rationale, sp.created_at
            FROM skill_proficiency sp
            JOIN documents d ON d.doc_id = sp.doc_id
            LEFT JOIN consents c ON c.doc_id = d.doc_id::text AND c.user_id = :user_id
            WHERE sp.skill_id = :skill_id
              AND (c.user_id = :user_id OR d.doc_id IN (
                  SELECT doc_id FROM consents WHERE user_id = :user_id
              ))
            ORDER BY sp.created_at DESC
            LIMIT 1
        """)
        row = db.execute(sql, {"user_id": user_id, "skill_id": skill_id}).mappings().first()
        
        if not row:
            return {"user_id": user_id, "skill_id": skill_id, "level": None, "message": "No proficiency record found for this user/skill combination"}
        
        return {"user_id": user_id, "skill_id": skill_id, "proficiency": dict(row)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/proficiency/user/skill failed: {type(e).__name__}: {e}")


@router.get("")
def list_proficiency(
    doc_id: str = Query(..., description="documents.doc_id"),
    latest_per_skill: bool = Query(default=True, description="if true, return newest row per skill_id"),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names(schema="public"))
        if "skill_proficiency" not in tables:
            raise RuntimeError("skill_proficiency table not found")

        cols = set(_table_cols("skill_proficiency"))

        want = []
        for c in ["prof_id","doc_id","skill_id","level","label","rationale","best_evidence","signals","meta","created_at"]:
            if c in cols:
                want.append(c)
        if not want:
            raise RuntimeError("no usable columns in skill_proficiency")

        if latest_per_skill:
            # postgres DISTINCT ON
            sql = text(
                f"""
                SELECT DISTINCT ON (skill_id) {', '.join(want)}
                FROM skill_proficiency
                WHERE doc_id = :doc_id
                ORDER BY skill_id, created_at DESC
                LIMIT :limit
                """
            )
            rows = db.execute(sql, {"doc_id": doc_id, "limit": int(limit)}).mappings().all()
            items = [dict(r) for r in rows]
            # count = number of returned skills
            total = len(items)
        else:
            sql = text(
                f"""
                SELECT {', '.join(want)}
                FROM skill_proficiency
                WHERE doc_id = :doc_id
                ORDER BY created_at DESC
                LIMIT :limit
                """
            )
            rows = db.execute(sql, {"doc_id": doc_id, "limit": int(limit)}).mappings().all()
            items = [dict(r) for r in rows]
            csql = text("SELECT COUNT(*) FROM skill_proficiency WHERE doc_id = :doc_id")
            total = int(db.execute(csql, {"doc_id": doc_id}).scalar() or 0)

        # normalize jsonb
        for it in items:
            for k in ["best_evidence", "signals", "meta"]:
                if k in it:
                    it[k] = _coerce_json(it.get(k)) or {}

        return {"doc_id": doc_id, "count": int(total), "items": items}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/proficiency failed: {type(e).__name__}: {e}")
