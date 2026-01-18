import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from sqlalchemy import text
from backend.app.db.deps import get_db
from backend.app.api.schemas import SkillIn, SkillOut, ImportResult
from backend.app.services.skills import upsert_skill, search_skills
from backend.app.models import Skill
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import inspect, text
from backend.app.db.session import SessionLocal, engine

def _coerce_json(v):
    """
    Accept JSON from DB as dict/list OR as JSON string.
    Returns Python object or None.
    """
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, (str, bytes, bytearray)):
        return json.loads(v)
    # last resort: try to stringify then parse (keeps API stable)
    return json.loads(str(v))

router = APIRouter(prefix="/skills", tags=["skills"])

@router.get("", response_model=list[SkillOut])
def list_or_search(
    q: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    List skills or search by q. Uses parameterized ILIKE so q='HKU' won't 500.
    Also tolerates level_rubric_json being either JSON string or already a dict.
    """
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names(schema="public"))
        if "skills" not in tables:
            raise RuntimeError(f"'skills' table not found. public tables={sorted(tables)[:50]}")

        cols = [c["name"] for c in insp.get_columns("skills", schema="public")]

        # choose a stable projection
        want = []
        for c in ["skill_id", "canonical_name", "aliases", "definition", "evidence_rules", "level_rubric_json", "version", "source"]:
            if c in cols and c not in want:
                want.append(c)
        if not want:
            want = cols[: min(len(cols), 12)]

        base_sql = f"SELECT {', '.join(want)} FROM skills"
        params = {"limit": limit}

        where = ""
        if q is not None and str(q).strip() != "":
            params["q"] = f"%{str(q).strip()}%"
            conds = []
            if "canonical_name" in cols:
                conds.append("canonical_name ILIKE :q")
            if "definition" in cols:
                conds.append("definition ILIKE :q")
            if "skill_id" in cols:
                conds.append("skill_id ILIKE :q")
            if not conds:
                conds = ["1=1"]
            where = " WHERE " + " OR ".join(conds)

        order = ""
        if "canonical_name" in cols:
            order = " ORDER BY canonical_name NULLS LAST"
        elif "skill_id" in cols:
            order = " ORDER BY skill_id NULLS LAST"

        sql = text(base_sql + where + order + " LIMIT :limit")
        rows = db.execute(sql, params).mappings().all()

        out = []
        for r in rows:
            d = dict(r)
            # normalize rubric
            if "level_rubric_json" in d:
                v = d.get("level_rubric_json")
                if isinstance(v, str):
                    try:
                        d["level_rubric"] = json.loads(v)
                    except Exception:
                        d["level_rubric"] = v
                else:
                    # already dict/list/None
                    d["level_rubric"] = v
            out.append(d)
        return out

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/skills failed: {type(e).__name__}: {e}")
@router.post("/import", response_model=ImportResult)
def import_skills(items: list[SkillIn], db: Session = Depends(get_db)):
    inserted = updated = skipped = 0
    errors: list[str] = []
    for it in items:
        try:
            created = upsert_skill(db, it.model_dump())
            inserted += 1 if created else 0
            updated += 0 if created else 1
        except Exception as e:
            skipped += 1
            errors.append(f"{it.skill_id}: {e}")
    db.commit()
    return ImportResult(inserted=inserted, updated=updated, skipped=skipped, errors=errors)
