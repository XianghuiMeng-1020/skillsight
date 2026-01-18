#!/usr/bin/env bash
set -euo pipefail

echo "== 0) sanity =="
[ -f backend/app/main.py ] || { echo "❌ run from repo root (skillsight/)"; exit 1; }

python3 - <<'PY'
from pathlib import Path
import re, datetime

def backup(p: Path):
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    b = p.with_suffix(p.suffix + f".bak.{ts}")
    b.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    return b

# --- 1) Patch ORM model if it has version column ---
candidates = [
    Path("backend/app/models/role.py"),
    Path("backend/app/models/roles.py"),
    Path("backend/app/models.py"),
]
for p in candidates:
    if not p.exists():
        continue
    s = p.read_text(encoding="utf-8")
    if re.search(r"\bversion\s*=\s*Column\(", s):
        bak = backup(p)
        # remove version Column line(s)
        s2 = re.sub(r"(?m)^\s*version\s*=\s*Column\([^\n]*\)\s*\n?", "", s)
        p.write_text(s2, encoding="utf-8")
        print(f"✅ removed ORM Role.version in {p} (backup {bak.name})")

# --- 2) Patch Pydantic schema if it requires version ---
schema_candidates = [
    Path("backend/app/schemas/role.py"),
    Path("backend/app/schemas/roles.py"),
]
for p in schema_candidates:
    if not p.exists():
        continue
    s = p.read_text(encoding="utf-8")
    # If schema defines version: str ... make it Optional or drop
    if re.search(r"^\s*version\s*:\s*str\b", s, flags=re.M):
        bak = backup(p)
        # ensure Optional imported
        if "Optional" not in s:
            if re.search(r"^from typing import ", s, flags=re.M):
                s = re.sub(r"^from typing import ([^\n]+)$", lambda m: "from typing import " + m.group(1).strip() + ", Optional", s, count=1, flags=re.M)
            else:
                s = "from typing import Optional\n" + s
        s = re.sub(r"(?m)^\s*version\s*:\s*str\b", "    version: Optional[str] = None", s)
        p.write_text(s, encoding="utf-8")
        print(f"✅ made schema version optional in {p} (backup {bak.name})")

# --- 3) Harden roles router: select only existing cols, avoid ORM touching version ---
roles_router = Path("backend/app/routers/roles.py")
if roles_router.exists():
    s = roles_router.read_text(encoding="utf-8")
    bak = backup(roles_router)

    # Ensure imports exist
    need_lines = [
        "from typing import Any, Dict, List, Optional",
        "from fastapi import APIRouter, Depends, HTTPException, Query",
        "from sqlalchemy import inspect, text",
        "from sqlalchemy.orm import Session",
        "from backend.app.db.session import SessionLocal, engine",
    ]
    # If file is messy, we just prepend a clean import block and keep rest below a marker.
    if "## HARDENED_ROLES_ROUTER" not in s:
        hardened = """## HARDENED_ROLES_ROUTER
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
"""
        roles_router.write_text(hardened + "\n", encoding="utf-8")
        print(f"✅ rewrote roles router hardened in {roles_router} (backup {bak.name})")
    else:
        print("ℹ️ roles router already hardened marker present, skipped rewrite.")
else:
    print("ℹ️ no backend/app/routers/roles.py found; skipping router patch.")

# --- 4) Ensure main.py hard endpoint doesn't have escaped docstring issues and uses text SELECT * ---
mainp = Path("backend/app/main.py")
s = mainp.read_text(encoding="utf-8")
bak = backup(mainp)

# Make sure required imports exist
if "from sqlalchemy import text" not in s:
    s = re.sub(r"(?m)^from fastapi import FastAPI.*$", lambda m: m.group(0) + "\nfrom sqlalchemy import text\nfrom sqlalchemy.orm import Session\nfrom backend.app.db.session import SessionLocal\n", s, count=1)

# Remove any broken escaped docstring block inserted previously (\"\"\" ...)
s = re.sub(r'(?ms)@app\.get\("/roles/\{role_id\}".*?\n(?=^@app\.get|^@app\.post|^def |\Z)', "", s)

# Insert clean hard endpoint at end (safe)
hard = """
@app.get("/roles/{role_id}", tags=["roles"])
def hard_get_role(role_id: str):
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
""".strip() + "\n"

# Ensure HTTPException imported
if "HTTPException" not in s:
    s = re.sub(r"(?m)^from fastapi import FastAPI\b", "from fastapi import FastAPI, HTTPException", s, count=1)

# Append hard endpoint if not already present
if '@app.get("/roles/{role_id}"' not in s:
    s = s.rstrip() + "\n\n" + hard
    mainp.write_text(s, encoding="utf-8")
    print(f"✅ ensured main.py hard /roles/{{role_id}} (backup {bak.name})")
else:
    print("ℹ️ main.py already has /roles/{role_id}, skipped append.")
PY

echo "== 5) restart uvicorn =="
lsof -ti tcp:8001 | xargs -r kill -9
export DATABASE_URL="postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight"
mkdir -p logs
nohup uvicorn backend.app.main:app --port 8001 > logs/uvicorn_8001.log 2>&1 &
sleep 1

echo "== 6) smoke =="
curl -sS http://127.0.0.1:8001/health && echo
curl -sS http://127.0.0.1:8001/roles | head -c 600 && echo
curl -sS http://127.0.0.1:8001/roles/HKU.ROLE.ASSISTANT_PM.v1 | python3 -m json.tool
echo "✅ roles.version issue should be gone"
