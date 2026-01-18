#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

python3 - <<'PY'
from pathlib import Path
import re, datetime

p = Path("backend/app/main.py")
s = p.read_text(encoding="utf-8")
bak = p.with_suffix(p.suffix + ".bak." + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
bak.write_text(s, encoding="utf-8")

# Ensure imports
need = [
    "from sqlalchemy import text",
    "from backend.app.db.session import SessionLocal",
]
for line in need:
    if line not in s:
        s = line + "\n" + s

# If a hard /skills already exists, skip
if re.search(r"@app\.get\(\s*[\"']\/skills[\"']\s*\)", s):
    print("ℹ️ main.py already defines @app.get('/skills') somewhere. Not adding another.")
    p.write_text(s, encoding="utf-8")
    raise SystemExit(0)

endpoint = r'''
@app.get("/skills")
def skills_list(q: str = "", limit: int = 50):
    """
    Hard-wired fallback endpoint for demo.
    If q is provided, filters by canonical_name or skill_id (ILIKE).
    """
    db = SessionLocal()
    try:
        limit = max(1, min(int(limit), 500))
        q2 = (q or "").strip()
        if q2:
            rows = db.execute(
                text("""
                    SELECT * FROM skills
                    WHERE (canonical_name ILIKE :q OR skill_id ILIKE :q)
                    ORDER BY canonical_name NULLS LAST
                    LIMIT :limit
                """),
                {"q": f"%{q2}%", "limit": limit},
            ).mappings().all()
        else:
            rows = db.execute(
                text("""
                    SELECT * FROM skills
                    ORDER BY canonical_name NULLS LAST
                    LIMIT :limit
                """),
                {"limit": limit},
            ).mappings().all()
        return {"status": "ok", "count": len(rows), "items": [dict(r) for r in rows]}
    finally:
        db.close()
'''
# Append after /roles block if present, else end
s = s.rstrip() + "\n\n" + endpoint.strip() + "\n"
p.write_text(s, encoding="utf-8")
print(f"✅ Patched {p} with hard /skills (backup: {bak.name})")
PY

echo "✅ Done. Restart uvicorn to load changes."
