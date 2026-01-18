#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== 0) Kill EVERYTHING on :8001 =="
PIDS="$(lsof -nP -iTCP:8001 -sTCP:LISTEN 2>/dev/null | awk 'NR>1{print $2}' | sort -u || true)"
if [ -n "${PIDS:-}" ]; then
  echo "Killing PIDs: $PIDS"
  for p in $PIDS; do kill -9 "$p" || true; done
fi
sleep 0.5
lsof -nP -iTCP:8001 -sTCP:LISTEN || echo "✅ 8001 is free"

echo
echo "== 1) Patch backend/app/main.py to add hard /roles endpoint =="
python3 - <<'PY'
from pathlib import Path
import re, datetime

p = Path("backend/app/main.py")
if not p.exists():
    raise SystemExit("backend/app/main.py not found")

s = p.read_text(encoding="utf-8")
bak = p.with_suffix(p.suffix + ".bak." + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
bak.write_text(s, encoding="utf-8")

# Ensure imports needed for DB query endpoint
need_lines = [
    "from sqlalchemy import text",
    "from backend.app.db.session import SessionLocal",
]
for line in need_lines:
    if line not in s:
        # insert after FastAPI import if possible
        m = re.search(r"^from fastapi import FastAPI.*$", s, flags=re.M)
        if m:
            i = m.end()
            s = s[:i] + "\n" + line + s[i:]
        else:
            s = line + "\n" + s

# Add endpoint only if not already present
if re.search(r"@app\.get\(\s*[\"']\/roles[\"']\s*\)", s):
    print("✅ main.py already has /roles endpoint; no change")
    raise SystemExit(0)

endpoint = r'''
@app.get("/roles")
def roles_list(limit: int = 50):
    """
    Hard-wired fallback endpoint to avoid router wiring issues.
    Returns rows from public.roles.
    """
    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT * FROM roles ORDER BY 1 NULLS LAST LIMIT :limit"),
            {"limit": max(1, min(int(limit), 500))},
        ).mappings().all()
        return {"status": "ok", "count": len(rows), "items": [dict(r) for r in rows]}
    finally:
        db.close()
'''

# Insert after /stats endpoint if it exists; else append
insert_after = None
m = re.search(r"@app\.get\(\s*[\"']\/stats[\"']\s*\)[\s\S]*?(?=^@app\.get|\Z)", s, flags=re.M)
if m:
    insert_after = m.end()

if insert_after is not None:
    s = s[:insert_after] + "\n\n" + endpoint.strip() + "\n" + s[insert_after:]
else:
    s = s.rstrip() + "\n\n" + endpoint.strip() + "\n"

p.write_text(s, encoding="utf-8")
print(f"✅ Patched {p} with hard /roles (backup: {bak.name})")
PY

echo
echo "== 2) Start uvicorn cleanly (NO --reload) =="
mkdir -p logs
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight}"
nohup uvicorn backend.app.main:app --port 8001 > logs/uvicorn_8001.log 2>&1 &

sleep 1

echo
echo "== 3) Verify /__routes contains /roles =="
curl -sS http://127.0.0.1:8001/__routes | python3 -m json.tool | grep -n "\"/roles\"" -n || true

echo
echo "== 4) Call /roles =="
curl -sS http://127.0.0.1:8001/roles | head -c 800 && echo

echo
echo "== Tail uvicorn log =="
tail -n 80 logs/uvicorn_8001.log
