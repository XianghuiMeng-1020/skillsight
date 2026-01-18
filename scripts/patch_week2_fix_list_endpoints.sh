#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Repo root: $ROOT"

python - <<'PY'
from __future__ import annotations
import re
from pathlib import Path
from datetime import datetime

def backup(p: Path) -> Path:
    bak = p.with_suffix(p.suffix + f".bak.{datetime.now().strftime('%Y%m%d%H%M%S')}")
    bak.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    return bak

# -------------------------
# 1) main.py: remove any direct @app.get("/skills") / @app.get("/roles") blocks
#    so only routers handle those paths (prevents duplicate route confusion).
# -------------------------
main = Path("backend/app/main.py")
if not main.exists():
    raise SystemExit("❌ backend/app/main.py not found")

s = main.read_text(encoding="utf-8")
bak = backup(main)

def drop_app_get_block(text: str, path: str) -> str:
    # Drop blocks like:
    # @app.get("/skills"...)
    # def ...:
    #     ...
    # (until next decorator @app., @router., or end)
    pat = re.compile(rf'^\s*@app\.get\(\s*["\']{re.escape(path)}["\'][^\)]*\)\s*\n'
                     r'^\s*def\s+[A-Za-z_]\w*\s*\([^)]*\)\s*:\s*\n'
                     r'(?:^(?:[ \t]+).*\n)*',
                     flags=re.M)
    return re.sub(pat, "", text)

s2 = drop_app_get_block(s, "/skills")
s2 = drop_app_get_block(s2, "/roles")

# Also drop any accidental duplicate include_router calls for the same router var names
# (very light touch: remove consecutive duplicate lines).
lines = s2.splitlines(True)
out = []
seen = set()
for ln in lines:
    key = ln.strip()
    if key.startswith("app.include_router("):
        # don't over-dedupe unrelated routers, only exact duplicates
        if key in seen:
            continue
        seen.add(key)
    out.append(ln)
s2 = "".join(out)

main.write_text(s2, encoding="utf-8")
print(f"✅ Patched {main} (backup: {bak.name})")


# -------------------------
# 2) skills.py: robust DB-backed list/search with table auto-detection
# -------------------------
skills_py = Path("backend/app/skills.py")
bak = backup(skills_py) if skills_py.exists() else None

skills_py.write_text(
r'''from __future__ import annotations

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
''',
encoding="utf-8")
print(f"✅ Wrote {skills_py}" + (f" (backup: {bak.name})" if bak else ""))


# -------------------------
# 3) roles.py: robust list + get_role, dict-safe return
# -------------------------
roles_py = Path("backend/app/roles.py")
bak = backup(roles_py) if roles_py.exists() else None

roles_py.write_text(
r'''from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text, inspect
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
def list_roles_alias(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        cols = _roles_columns()
        want = []
        for c in ["role_id", "role_title", "description", "source", "version"]:
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
        cols = _roles_columns()
        sql = text("SELECT * FROM roles WHERE role_id = :rid LIMIT 1")
        row = db.execute(sql, {"rid": role_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail=f"role_id not found: {role_id}")
        return {"status": "ok", "item": dict(row)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/roles/{{role_id}} failed: {type(e).__name__}: {e}")
''',
encoding="utf-8")
print(f"✅ Wrote {roles_py}" + (f" (backup: {bak.name})" if bak else ""))

PY

echo ""
echo "✅ patch_week2_fix_list_endpoints applied."
echo ""
echo "Next:"
echo "  1) export DATABASE_URL='postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight'"
echo "  2) lsof -nP -iTCP:8001 -sTCP:LISTEN || true"
echo "  3) uvicorn backend.app.main:app --port 8001"
echo "  4) curl -sS 'http://127.0.0.1:8001/skills?q=' | head"
echo "  5) curl -sS 'http://127.0.0.1:8001/roles' | head"
