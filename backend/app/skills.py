from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal, engine

router = APIRouter(tags=["skills"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _pick_skills_table_and_columns() -> Tuple[str, List[str], Optional[str]]:
    """
    Pick a skills-like table at runtime.
    Priority:
      1) 'skills' table if exists
      2) any table with 'skill_id' AND ('canonical_name' OR 'name')
    Returns: (table_name, columns, name_col)
    """
    insp = inspect(engine)
    tables = set(insp.get_table_names(schema="public"))

    if "skills" in tables:
        cols = [c["name"] for c in insp.get_columns("skills", schema="public")]
        name_col = "canonical_name" if "canonical_name" in cols else ("name" if "name" in cols else None)
        return "skills", cols, name_col

    # find a best candidate
    best = None
    for t in sorted(tables):
        cols = [c["name"] for c in insp.get_columns(t, schema="public")]
        if "skill_id" not in cols:
            continue
        name_col = None
        if "canonical_name" in cols:
            name_col = "canonical_name"
        elif "name" in cols:
            name_col = "name"
        if name_col:
            best = (t, cols, name_col)
            break

    if best:
        return best

    raise RuntimeError(f"No skills-like table found in public schema. Tables={sorted(tables)[:50]}")

@router.get("/skills")
def list_or_search(
    q: Optional[str] = Query(default=None, description="optional search term"),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        table, cols, name_col = _pick_skills_table_and_columns()
        # choose projection (stable + useful)
        want = []
        for c in ["skill_id", "canonical_name", "name", "definition", "version", "source"]:
            if c in cols and c not in want:
                want.append(c)
        if not want:
            want = cols[: min(len(cols), 12)]

        where = ""
        params: Dict[str, Any] = {"limit": limit}

        if q and q.strip():
            qq = f"%{q.strip().lower()}%"
            params["q"] = qq
            conds = []
            if "skill_id" in cols:
                conds.append("LOWER(CAST(skill_id AS TEXT)) LIKE :q")
            if name_col:
                conds.append(f"LOWER(CAST({name_col} AS TEXT)) LIKE :q")
            if "definition" in cols:
                conds.append("LOWER(CAST(definition AS TEXT)) LIKE :q")
            if conds:
                where = "WHERE " + " OR ".join(conds)

        sql = text(f"SELECT {', '.join(want)} FROM {table} {where} ORDER BY 1 NULLS LAST LIMIT :limit")
        rows = db.execute(sql, params).mappings().all()
        return {
            "status": "ok",
            "table": table,
            "count": len(rows),
            "items": [dict(r) for r in rows],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/skills failed: {type(e).__name__}: {e}")
