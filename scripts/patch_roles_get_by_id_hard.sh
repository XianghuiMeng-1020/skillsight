#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FILE="$ROOT/backend/app/main.py"

python3 - <<'PY'
from pathlib import Path
import re, datetime

p = Path("backend/app/main.py")
s = p.read_text(encoding="utf-8")
bak = p.with_suffix(p.suffix + f".bak.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}")
bak.write_text(s, encoding="utf-8")

# Ensure needed imports exist in main.py
need_lines = [
    "from sqlalchemy import text",
    "from sqlalchemy.orm import Session",
    "from fastapi import HTTPException",
]
for line in need_lines:
    if line not in s:
        # insert after FastAPI import block if possible, else top
        m = re.search(r"(?m)^from fastapi import .*$", s)
        if m:
            insert_at = m.end()
            s = s[:insert_at] + "\n" + line + s[insert_at:]
        else:
            s = line + "\n" + s

# Ensure SessionLocal exists import (your project already has this in many patches)
if "from backend.app.db.session import SessionLocal" not in s:
    # try to insert near other db imports
    m = re.search(r"(?m)^from backend\.app\.db\.session import .*?$", s)
    if m:
        pass
    else:
        s = "from backend.app.db.session import SessionLocal\n" + s

# Ensure get_db dependency exists
if not re.search(r"(?ms)^def\s+get_db\s*\(\)\s*:\s*\n.*?yield\s+db", s):
    # Add a minimal get_db near top-level, after app creation if possible
    block = """
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
""".strip() + "\n\n"
    # insert after app = FastAPI(...)
    m = re.search(r"(?m)^app\s*=\s*FastAPI\(.*\)\s*$", s)
    if m:
        s = s[:m.end()] + "\n\n" + block + s[m.end():]
    else:
        s = block + s

# Hard endpoint for /roles/{role_id}
replacement = r"""
@app.get("/roles/{role_id}")
def hard_get_role(role_id: str, db: Session = Depends(get_db)):
    \"\"\"Fetch a single role by role_id (hard-wired safe SQL).\"\"\"
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
""".strip() + "\n\n"

# If an existing hard_get_role exists, replace it; else append near other hard endpoints.
pat_existing = r"(?ms)^@app\.get\(\"/roles/\{role_id\}\"\)\n.*?\n(?=^@app\.|^if __name__ ==|^$|\Z)"
m = re.search(pat_existing, s)
if m:
    s = re.sub(pat_existing, replacement, s, count=1)
else:
    # append after hard /roles if present, else near end
    m2 = re.search(r"(?ms)^@app\.get\(\"/roles\"\)\n.*?\n(?=^@app\.|^if __name__ ==|\Z)", s)
    if m2:
        insert_at = m2.end()
        s = s[:insert_at] + "\n\n" + replacement + s[insert_at:]
    else:
        s = s.rstrip() + "\n\n" + replacement

p.write_text(s, encoding="utf-8")
print(f"✅ Patched {p} with hard GET /roles/{{role_id}}. backup: {bak.name}")
PY

echo "✅ patch_roles_get_by_id_hard applied."
echo "Next:"
echo "  lsof -ti tcp:8001 | xargs -r kill -9"
echo "  export DATABASE_URL='postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight'"
echo "  nohup uvicorn backend.app.main:app --port 8001 > logs/uvicorn_8001.log 2>&1 &"
echo "  sleep 1"
echo "  curl -sS http://127.0.0.1:8001/roles/HKU.ROLE.ASSISTANT_PM.v1 | head -c 900 && echo"
