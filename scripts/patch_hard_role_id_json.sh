#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
import re, datetime

p = Path("backend/app/main.py")
s = p.read_text(encoding="utf-8")
bak = p.with_suffix(".py.bak."+datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
bak.write_text(s, encoding="utf-8")

block = r'''
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import HTTPException

@app.get("/roles/{role_id}", tags=["roles"])
def hard_get_role(role_id: str):
    """Hard-wired role lookup to guarantee JSON output."""
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
'''.strip() + "\n"

# If an @app.get("/roles/{role_id}") already exists, do nothing.
if re.search(r'@app\.get\(\s*"/roles/\{role_id\}"', s):
    print("ℹ️ main.py already has hard /roles/{role_id}. No changes.")
else:
    # Insert after SessionLocal import if possible, else append.
    m = re.search(r"^from backend\.app\.db\.session import SessionLocal.*$", s, flags=re.M)
    if m:
        insert_at = m.end()
        s = s[:insert_at] + "\n\n" + block + s[insert_at:]
    else:
        s = s.rstrip() + "\n\n" + block
    p.write_text(s, encoding="utf-8")
    print(f"✅ Patched main.py hard /roles/{{role_id}}. backup: {bak.name}")
PY

echo "Restart uvicorn..."
lsof -ti tcp:8001 | xargs -r kill -9
export DATABASE_URL="postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight"
nohup uvicorn backend.app.main:app --port 8001 > logs/uvicorn_8001.log 2>&1 &
sleep 1
curl -sS "http://127.0.0.1:8001/roles/HKU.ROLE.ASSISTANT_PM.v1" | python3 -m json.tool
