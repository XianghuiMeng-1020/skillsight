#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python}"
if ! command -v "$PY" >/dev/null 2>&1; then
  PY="python3"
fi

MAIN="backend/app/main.py"
if [ ! -f "$MAIN" ]; then
  echo "❌ $MAIN not found. Aborting."
  exit 1
fi

TS="$(date +%Y%m%d%H%M%S)"
cp "$MAIN" "$MAIN.bak.$TS"

echo "🔧 Patching $MAIN (backup: $MAIN.bak.$TS)"

"$PY" - <<'PY'
from pathlib import Path
import re

p = Path("backend/app/main.py")
s = p.read_text(encoding="utf-8")

# --- 1) Ensure a /routes debug endpoint exists (so we can see what is mounted) ---
if "/__routes" not in s:
    insert_anchor = "app = FastAPI"
    m = re.search(r"app\s*=\s*FastAPI\([^\n]*\)\s*", s)
    if not m:
        raise SystemExit("Cannot find app = FastAPI(...) line to anchor patch.")
    block = r'''
from fastapi.responses import JSONResponse

@app.get("/__routes")
def __routes():
    return JSONResponse([
        {"path": r.path, "name": r.name, "methods": sorted(list(getattr(r, "methods", []) or []))}
        for r in app.router.routes
    ])
'''.lstrip("\n")
    s = s[:m.end()] + "\n\n" + block + "\n" + s[m.end():]

# --- 2) Ensure roles router has a GET /roles (or /roles/), add a safe alias if missing ---
# Heuristic: if main includes roles_router and includes_router already, then add a tiny alias endpoint here
needs_roles_get = True
if re.search(r'@app\.get\(["\']/roles', s):
    needs_roles_get = False

if needs_roles_get:
    # We'll implement GET /roles here, calling the underlying router handler if it exists,
    # otherwise do a direct DB query via SQLAlchemy models if present.
    block = r'''
@app.get("/roles")
def list_roles_alias():
    """
    Compatibility alias:
    Some earlier patches mounted roles endpoints under /roles/ or only had /roles/import.
    This provides a stable GET /roles for the web demo.
    """
    try:
        # Try calling router function if it exists (backend.app.routers.roles: list_roles)
        from backend.app.routers.roles import list_roles  # type: ignore
        return list_roles()
    except Exception:
        # Fallback: direct DB query
        from backend.app.db.session import SessionLocal
        from backend.app.models.role import Role  # type: ignore
        db = SessionLocal()
        try:
            rows = db.query(Role).order_by(Role.role_title.asc()).all()
            return [r.to_dict() if hasattr(r, "to_dict") else {"id": getattr(r, "id", None), "role_id": getattr(r, "role_id", None), "role_title": getattr(r, "role_title", None)} for r in rows]
        finally:
            db.close()
'''.lstrip("\n")
    # Append near end
    s = s.rstrip() + "\n\n" + block + "\n"

# --- 3) Patch /skills endpoint to be robust with q empty and avoid 500 ---
# If there's an existing @app.get("/skills") in main, replace it with a safe version.
skills_pattern = re.compile(r'@app\.get\(["\']/skills["\']\)\s*\n(?:.|\n)*?(?=\n@app\.|\Z)', re.M)

replacement = r'''
@app.get("/skills")
def list_skills(q: str = ""):
    """
    List skills with optional substring search on canonical_name or aliases.
    Safe for q="" (returns a small default list).
    """
    from backend.app.db.session import SessionLocal
    db = SessionLocal()
    try:
        # Prefer ORM model if present
        try:
            from backend.app.models.skill import Skill  # type: ignore
            query = db.query(Skill)
            if q:
                like = f"%{q}%"
                # canonical_name is common; aliases may be a separate table, so keep it simple here
                if hasattr(Skill, "canonical_name"):
                    query = query.filter(Skill.canonical_name.ilike(like))
            rows = query.limit(50).all()
            out = []
            for r in rows:
                if hasattr(r, "to_dict"):
                    out.append(r.to_dict())
                else:
                    out.append({
                        "id": getattr(r, "id", None),
                        "skill_id": getattr(r, "skill_id", None),
                        "canonical_name": getattr(r, "canonical_name", None),
                        "definition": getattr(r, "definition", None),
                        "version": getattr(r, "version", None),
                        "source": getattr(r, "source", None),
                    })
            return out
        except Exception:
            # Fallback to raw SQL if model import fails
            from sqlalchemy import text
            if q:
                rows = db.execute(text("""
                    SELECT skill_id, canonical_name, definition, version, source
                    FROM skill_proficiency
                    WHERE canonical_name ILIKE :like
                    ORDER BY canonical_name ASC
                    LIMIT 50
                """), {"like": f"%{q}%"}).fetchall()
            else:
                rows = db.execute(text("""
                    SELECT skill_id, canonical_name, definition, version, source
                    FROM skill_proficiency
                    ORDER BY canonical_name ASC
                    LIMIT 50
                """)).fetchall()
            return [
                {"skill_id": r[0], "canonical_name": r[1], "definition": r[2], "version": r[3], "source": r[4]}
                for r in rows
            ]
    except Exception as e:
        # Return visible error for debugging instead of silent 500
        return {"status": "error", "where": "/skills", "error": str(e)}
    finally:
        db.close()
'''.lstrip("\n")

if skills_pattern.search(s):
    s = skills_pattern.sub(replacement + "\n", s, count=1)
else:
    s = s.rstrip() + "\n\n" + replacement + "\n"

p.write_text(s, encoding="utf-8")
print("✅ Patched main.py: added /__routes, ensured GET /roles, hardened GET /skills")
PY

echo ""
echo "✅ Patch applied."
echo "Next:"
echo "  1) Kill old server if needed: lsof -nP -iTCP:8001 -sTCP:LISTEN"
echo "  2) export DATABASE_URL='postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight'"
echo "  3) uvicorn backend.app.main:app --reload --port 8001"
echo "  4) curl -sS http://127.0.0.1:8001/__routes | head"
echo "  5) curl -sS 'http://127.0.0.1:8001/skills?q=' | head"
echo "  6) curl -sS http://127.0.0.1:8001/roles | head"
