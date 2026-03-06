import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from backend.app.db.deps import get_db
from backend.app.db.session import engine
from backend.app.security import require_auth

router = APIRouter(prefix="/skills", tags=["skills"], dependencies=[Depends(require_auth)])


def _now_utc():
    return datetime.now(timezone.utc)


def _table_cols(table: str) -> List[str]:
    insp = inspect(engine)
    return [c["name"] for c in insp.get_columns(table, schema="public")]


def _col_udt_map(db: Session, table: str) -> Dict[str, str]:
    sql = text(
        """
        SELECT column_name, udt_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:t
        """
    )
    rows = db.execute(sql, {"t": table}).mappings().all()
    return {r["column_name"]: r["udt_name"] for r in rows}


def _loads_maybe(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return v
        try:
            return json.loads(s)
        except Exception:
            return v
    return v


def _insert_one(db: Session, table: str, data: Dict[str, Any]) -> None:
    cols = set(_table_cols(table))
    use = {k: v for k, v in data.items() if k in cols}
    if not use:
        raise RuntimeError(f"no usable columns to insert into {table}")

    udt = _col_udt_map(db, table)
    keys = list(use.keys())
    placeholders = []
    for k in keys:
        tname = (udt.get(k) or "").lower()
        v = use.get(k)
        if tname in ("jsonb", "json"):
            if v is None:
                use[k] = "null"
            elif not isinstance(v, str):
                use[k] = json.dumps(v, ensure_ascii=False)
        elif isinstance(v, (dict, list)):
            # text column but value is dict/list — serialize to JSON string
            use[k] = json.dumps(v, ensure_ascii=False)
        if tname == "jsonb":
            placeholders.append(f"CAST(:{k} AS JSONB)")
        elif tname == "json":
            placeholders.append(f"CAST(:{k} AS JSON)")
        else:
            placeholders.append(f":{k}")

    sql = text(f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({', '.join(placeholders)})")
    db.execute(sql, use)


@router.get("")
def list_or_search(
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List or search skills. Returns {items: [...]} format for frontend compatibility.
    """
    try:
        cols = _table_cols("skills")
        if not cols:
            return {"items": [], "count": 0}

        want = []
        for c in ["skill_id", "canonical_name", "aliases", "definition", "evidence_rules", "level_rubric", "version", "source", "created_at"]:
            if c in cols:
                want.append(c)
        if not want:
            want = cols[: min(12, len(cols))]

        where = ""
        params: Dict[str, Any] = {"limit": limit}
        if q and q.strip():
            qq = f"%{q.strip().lower()}%"
            # alias may be jsonb or text; we just cast to text for search
            clauses = []
            if "skill_id" in cols:
                clauses.append("LOWER(skill_id) LIKE :qq")
            if "canonical_name" in cols:
                clauses.append("LOWER(canonical_name) LIKE :qq")
            if "definition" in cols:
                clauses.append("LOWER(definition) LIKE :qq")
            if "aliases" in cols:
                clauses.append("LOWER(CAST(aliases AS TEXT)) LIKE :qq")
            where = " WHERE " + " OR ".join(clauses) if clauses else ""
            params["qq"] = qq

        sql = text(f"SELECT {', '.join(want)} FROM skills{where} ORDER BY skill_id ASC LIMIT :limit")
        rows = db.execute(sql, params).mappings().all()

        out = []
        for r in rows:
            d = dict(r)
            if "aliases" in d:
                d["aliases"] = _loads_maybe(d.get("aliases")) or []
            if "level_rubric" in d:
                d["level_rubric"] = _loads_maybe(d.get("level_rubric")) or {}
            out.append(d)
        return {"items": out, "count": len(out)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/skills failed: {type(e).__name__}: {e}")


@router.get("/search")
def search_skills(
    query: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Search skills by query. Alias for GET /skills?q=xxx for API consistency.
    """
    search_term = query or q
    return list_or_search(q=search_term, limit=limit, db=db)


@router.post("/import")
def import_skills(payload: List[Dict[str, Any]], db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Upsert by skill_id. Works across evolving schemas.
    """
    try:
        cols = set(_table_cols("skills"))
        if "skill_id" not in cols:
            raise RuntimeError("skills.skill_id column missing")

        udt = _col_udt_map(db, "skills")
        now = _now_utc()

        inserted = 0
        updated = 0

        for s in payload or []:
            sid = (s.get("skill_id") or "").strip()
            if not sid:
                continue

            exists = db.execute(text("SELECT 1 FROM skills WHERE skill_id=:sid LIMIT 1"), {"sid": sid}).scalar()
            data: Dict[str, Any] = {"skill_id": sid}

            for k in ["canonical_name","aliases","definition","evidence_rules","level_rubric","level_rubric_json","version","source"]:
                if k in cols and k in s:
                    data[k] = s.get(k)
            # Map level_rubric -> level_rubric_json for schema compatibility
            if "level_rubric_json" in cols and "level_rubric" in s and "level_rubric_json" not in data:
                data["level_rubric_json"] = s.get("level_rubric")

            if "updated_at" in cols:
                data["updated_at"] = now
            if "created_at" in cols and not exists:
                data["created_at"] = now

            # update path
            if exists:
                set_parts = []
                params: Dict[str, Any] = {"skill_id": sid}
                for k, v in data.items():
                    if k == "skill_id":
                        continue
                    tname = (udt.get(k) or "").lower()
                    if tname == "jsonb":
                        params[k] = json.dumps(v, ensure_ascii=False)  # Always JSON-encode for JSONB
                        set_parts.append(f"{k} = CAST(:{k} AS JSONB)")
                    elif tname == "json":
                        params[k] = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
                        set_parts.append(f"{k} = CAST(:{k} AS JSON)")
                    else:
                        params[k] = v
                        set_parts.append(f"{k} = :{k}")

                if set_parts:
                    db.execute(text(f"UPDATE skills SET {', '.join(set_parts)} WHERE skill_id=:skill_id"), params)
                    updated += 1
                continue

            # insert path
            _insert_one(db, "skills", data)
            inserted += 1

        db.commit()
        return {"inserted": inserted, "updated": updated, "n": inserted + updated}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"/skills/import failed: {type(e).__name__}: {e}")
