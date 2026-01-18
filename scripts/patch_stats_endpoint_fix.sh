#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MAIN="backend/app/main.py"
if [ ! -f "$MAIN" ]; then
  echo "❌ $MAIN not found"
  exit 1
fi

cp "$MAIN" "$MAIN.bak.$(date +%Y%m%d%H%M%S)"

python - <<'PY'
from pathlib import Path
import re

p = Path("backend/app/main.py")
s = p.read_text(encoding="utf-8")

# If /stats already exists, remove old injected block (to avoid duplicates)
s = re.sub(r"\n@app\.get\(\"/stats\"\)[\s\S]*?\n(?=@app\.get|@app\.post|@app\.put|@app\.delete|@app\.patch|$)", "\n", s, count=1)

# Ensure imports: text + SessionLocal fallback
if "from sqlalchemy import text" not in s:
    # insert after FastAPI import if present
    if re.search(r"from fastapi import FastAPI", s):
        s = re.sub(r"(from fastapi import FastAPI[^\n]*\n)",
                   r"\1from sqlalchemy import text\n", s, count=1)
    else:
        s = "from sqlalchemy import text\n" + s

if "SessionLocal" not in s:
    inject = """
try:
    from backend.app.db.session import SessionLocal  # type: ignore
except Exception:
    try:
        from backend.app.database import SessionLocal  # type: ignore
    except Exception:
        SessionLocal = None  # type: ignore
"""
    # put inject near imports top (after sqlalchemy import text)
    if "from sqlalchemy import text" in s:
        s = s.replace("from sqlalchemy import text\n", "from sqlalchemy import text\n" + inject + "\n", 1)
    else:
        s = inject + "\n" + s

stats_block = """
@app.get("/stats")
def stats():
    # Lightweight counts for demo smoke-check.
    if SessionLocal is None:
        return {"error": "SessionLocal not found; check backend/app/db/session.py or backend/app/database.py"}
    db = SessionLocal()
    try:
        skills = db.execute(text("SELECT COUNT(1) FROM skills")).scalar() or 0
        roles  = db.execute(text("SELECT COUNT(1) FROM roles")).scalar() or 0
        return {"skills": int(skills), "roles": int(roles)}
    finally:
        db.close()
"""

# Insert after /health if possible; else append end
m = re.search(r'@app\.get\("/health"\)[\s\S]*?return\s*\{\s*"status"\s*:\s*"ok"\s*\}\s*', s)
if m:
    insert_at = m.end()
    s = s[:insert_at] + "\n" + stats_block + "\n" + s[insert_at:]
else:
    s = s.rstrip() + "\n\n" + stats_block + "\n"

p.write_text(s, encoding="utf-8")
print("✅ Patched backend/app/main.py (/stats) without docstring nesting issues")
PY

echo "✅ patch_stats_endpoint_fix applied."
echo "Next:"
echo "  uvicorn backend.app.main:app --reload --port 8001"
echo "  curl -s http://127.0.0.1:8001/stats"
