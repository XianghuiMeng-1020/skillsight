#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

py() { python3 - "$@"; }

echo "== Patch main.py router wiring =="
py <<'PY'
from pathlib import Path
import re, datetime

p = Path("backend/app/main.py")
if not p.exists():
    raise SystemExit("backend/app/main.py not found")

bak = p.with_suffix(p.suffix + ".bak." + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
s = p.read_text(encoding="utf-8")
bak.write_text(s, encoding="utf-8")

# Ensure imports exist (robust to different styles)
need_imports = [
    ("from backend.app.routers.skills import router as skills_router", "skills_router"),
    ("from backend.app.routers.roles import router as roles_router", "roles_router"),
]

for imp, name in need_imports:
    if imp not in s:
        # Insert after FastAPI import block (best-effort)
        m = re.search(r"^from fastapi import FastAPI.*$", s, flags=re.M)
        if m:
            insert_at = m.end()
            s = s[:insert_at] + "\n" + imp + s[insert_at:]
        else:
            s = imp + "\n" + s

# Ensure include_router calls exist
def ensure_include(name: str):
    pat = re.compile(rf"app\.include_router\(\s*{re.escape(name)}\s*\)")
    if not pat.search(s):
        # Put after app = FastAPI(...)
        m = re.search(r"^app\s*=\s*FastAPI\([^\n]*\)\s*$", s, flags=re.M)
        if not m:
            # fallback: append
            return s + f"\napp.include_router({name})\n"
        i = m.end()
        return s[:i] + f"\napp.include_router({name})" + s[i:]
    return s

s2 = s
s2 = ensure_include("skills_router")
s2 = ensure_include("roles_router")

p.write_text(s2, encoding="utf-8")
print(f"✅ Patched {p} (backup: {bak.name})")
PY

echo "== Patch roles router to ensure /roles exists =="
py <<'PY'
from pathlib import Path
import re, datetime

p = Path("backend/app/routers/roles.py")
if not p.exists():
    raise SystemExit("backend/app/routers/roles.py not found")

bak = p.with_suffix(p.suffix + ".bak." + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
s = p.read_text(encoding="utf-8")
bak.write_text(s, encoding="utf-8")

# If /roles already exists, do nothing.
if re.search(r"@router\.get\(\s*[\"']\/roles[\"']\s*\)", s):
    print("✅ roles.py already has @router.get('/roles') ; no change")
    raise SystemExit(0)

# Ensure minimal imports exist
needed = [
    "from fastapi import APIRouter, Depends, HTTPException, Query",
    "from sqlalchemy import text",
    "from sqlalchemy.orm import Session",
]
for line in needed:
    if line not in s:
        # Put near top
        s = line + "\n" + s

# Ensure router exists
if not re.search(r"router\s*=\s*APIRouter", s):
    s = "router = APIRouter(tags=['roles'])\n\n" + s

# Ensure get_db exists
if "def get_db" not in s:
    s += "\n\nfrom backend.app.db.session import SessionLocal\n\n"
    s += (
        "def get_db():\n"
        "    db = SessionLocal()\n"
        "    try:\n"
        "        yield db\n"
        "    finally:\n"
        "        db.close()\n"
    )

# Append a minimal /roles endpoint (safe, table-driven)
append = r'''
@router.get("/roles")
def list_roles(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Minimal list endpoint for demo.
    Returns rows from public.roles. Works even if schema evolves.
    """
    try:
        rows = db.execute(
            text("SELECT * FROM roles ORDER BY 1 NULLS LAST LIMIT :limit"),
            {"limit": limit},
        ).mappings().all()
        return {"status": "ok", "count": len(rows), "items": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/roles failed: {type(e).__name__}: {e}")
'''
s = s.rstrip() + "\n\n" + append.lstrip()

p.write_text(s, encoding="utf-8")
print(f"✅ Patched {p} to add /roles (backup: {bak.name})")
PY

echo "== Restart uvicorn on :8001 =="
PID=$(lsof -nP -iTCP:8001 -sTCP:LISTEN | awk 'NR==2{print $2}' || true)
if [ -n "${PID:-}" ]; then
  echo "Killing PID=$PID on :8001"
  kill -9 "$PID" || true
fi

mkdir -p logs
nohup uvicorn backend.app.main:app --port 8001 --reload > logs/uvicorn_8001.log 2>&1 &

sleep 1

echo "== Verify routes include /roles =="
curl -sS http://127.0.0.1:8001/__routes | python -m json.tool | grep -n "\"/roles" -n || true

echo
echo "== Call /roles =="
curl -sS http://127.0.0.1:8001/roles | head -c 600 && echo

echo
echo "== Tail log =="
tail -n 60 logs/uvicorn_8001.log
