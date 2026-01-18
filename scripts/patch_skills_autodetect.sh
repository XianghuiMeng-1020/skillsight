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
imports = [
    "from sqlalchemy import text, inspect",
    "from backend.app.db.session import SessionLocal, engine",
]
for imp in imports:
    if imp not in s:
        s = imp + "\n" + s

# Remove any previous hard /skills block we appended (best-effort)
s = re.sub(r"@app\.get\(\"/skills\"\)[\s\S]*?\n(?=@app\.get\(|\Z)", "", s, flags=re.M)

endpoint = r'''
@app.get("/skills")
def skills_list(q: str = "", limit: int = 50):
    """
    Demo endpoint. Auto-detect the real skills table name in public schema.
    Supports q search when columns exist.
    """
    insp = inspect(engine)
    tables = set(insp.get_table_names(schema="public"))
    candidates = ["skills", "skill_registry", "skill_proficiency", "skill_assessments", "skill_aliases"]
    table = next((t for t in candidates if t in tables), None)
    if not table:
        return {"status": "error", "detail": "no skills-like table found", "public_tables": sorted(list(tables))}

    cols = [c["name"] for c in insp.get_columns(table, schema="public")]
    limit = max(1, min(int(limit), 500))
    q2 = (q or "").strip()

    db = SessionLocal()
    try:
        # Prefer search on canonical_name/skill_id if present
        has_cn = "canonical_name" in cols
        has_sid = "skill_id" in cols

        if q2 and (has_cn or has_sid):
            parts = []
            if has_cn:
                parts.append("canonical_name ILIKE :q")
            if has_sid:
                parts.append("skill_id ILIKE :q")
            where = " OR ".join(parts)
            sql = text(f"""
                SELECT * FROM {table}
                WHERE ({where})
                ORDER BY 1 NULLS LAST
                LIMIT :limit
            """)
            rows = db.execute(sql, {"q": f"%{q2}%", "limit": limit}).mappings().all()
        else:
            sql = text(f"SELECT * FROM {table} ORDER BY 1 NULLS LAST LIMIT :limit")
            rows = db.execute(sql, {"limit": limit}).mappings().all()

        return {"status": "ok", "table": table, "count": len(rows), "items": [dict(r) for r in rows]}
    finally:
        db.close()
'''
s = s.rstrip() + "\n\n" + endpoint.strip() + "\n"
p.write_text(s, encoding="utf-8")
print(f"✅ Patched {p} with autodetect /skills (backup: {bak.name})")
PY
