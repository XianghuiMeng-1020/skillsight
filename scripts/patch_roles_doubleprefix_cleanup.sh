#!/usr/bin/env bash
set -euo pipefail

ROOT="$(pwd)"
MAIN="backend/app/main.py"
ROLES="backend/app/routers/roles.py"

if [ ! -f "$MAIN" ]; then
  echo "❌ $MAIN not found (run from repo root)."
  exit 1
fi
if [ ! -f "$ROLES" ]; then
  echo "❌ $ROLES not found."
  exit 1
fi

ts="$(date +%Y%m%d%H%M%S)"
cp "$MAIN"  "${MAIN}.bak.${ts}"
cp "$ROLES" "${ROLES}.bak.${ts}"
echo "✅ Backups:"
echo "  - ${MAIN}.bak.${ts}"
echo "  - ${ROLES}.bak.${ts}"

python3 - <<'PY'
from pathlib import Path
import re
from datetime import datetime

roles_path = Path("backend/app/routers/roles.py")
s = roles_path.read_text(encoding="utf-8")

# Fix double-prefix issue: if main.py includes router with prefix="/roles",
# then roles.py MUST NOT define @router.get("/roles") (should be "").
# Also avoid /roles/roles/{id} by fixing "/roles/{role_id}" -> "/{role_id}" if present.

# 1) normalize list endpoint
s2 = s
s2 = re.sub(r'@router\.get\(\s*["\']/roles["\']\s*\)', '@router.get("")', s2)
s2 = re.sub(r'@router\.get\(\s*["\']/roles/\{role_id\}["\']\s*\)', '@router.get("/{role_id}")', s2)

# 2) if someone wrote "/roles/" with trailing slash
s2 = re.sub(r'@router\.get\(\s*["\']/roles/["\']\s*\)', '@router.get("")', s2)

# 3) if router.get("/roles/{role_id}") with different param name, keep it safe:
# (optional) but we do not over-aggressively rewrite other patterns.

if s2 != s:
    roles_path.write_text(s2, encoding="utf-8")
    print("✅ Patched roles router paths to prevent /roles/roles.")
else:
    print("ℹ️ roles.py already looks OK (no @router.get('/roles') found).")

# Now remove hard-wired /roles and /roles/{role_id} from main.py (they cause duplicates).
main_path = Path("backend/app/main.py")
m = main_path.read_text(encoding="utf-8")

def drop_app_route(code: str, path: str) -> str:
    """
    Remove a top-level FastAPI route block that starts with:
      @app.get("<path>")
    and continues until next top-level decorator (@app.) OR EOF.
    """
    pattern = rf"(?ms)^[ \t]*@app\.get\(\s*['\"]{re.escape(path)}['\"].*?\n(?=^[ \t]*@app\.|\Z)"
    return re.sub(pattern, "", code)

m2 = m
m2 = drop_app_route(m2, "/roles")
m2 = drop_app_route(m2, "/roles/{role_id}")

# Also remove any duplicate alias route if somebody added it (rare):
m2 = drop_app_route(m2, "/roles/roles")

if m2 != m:
    # clean excessive blank lines
    m2 = re.sub(r"\n{4,}", "\n\n\n", m2)
    main_path.write_text(m2, encoding="utf-8")
    print("✅ Removed hard-wired /roles and /roles/{role_id} from main.py to avoid duplicate routes.")
else:
    print("ℹ️ main.py had no hard-wired /roles routes (or already removed).")
PY

echo
echo "✅ Patch applied. Restarting uvicorn on :8001 ..."
echo

# restart server cleanly
lsof -ti tcp:8001 | xargs -r kill -9 || true
mkdir -p logs

# keep existing DATABASE_URL if already exported; warn if not
if [ -z "${DATABASE_URL:-}" ]; then
  echo "⚠️ DATABASE_URL is not set in this shell. If your backend needs it, export it before starting."
fi

nohup uvicorn backend.app.main:app --port 8001 > logs/uvicorn_8001.log 2>&1 &
sleep 1

echo "== Verify /roles routes (should NOT include /roles/roles) =="
curl -sS http://127.0.0.1:8001/__routes | python3 -c 'import json,sys; r=json.load(sys.stdin); paths=[x["path"] for x in r]; print("has_/roles/roles =", "/roles/roles" in paths); print([p for p in paths if p.startswith("/roles")])'
echo
echo "== Verify openapi roles paths (should NOT include /roles/roles) =="
curl -sS http://127.0.0.1:8001/openapi.json | python3 -c 'import json,sys; o=json.load(sys.stdin); paths=o.get("paths",{}); print([p for p in sorted(paths) if p.startswith("/roles")])'
echo
echo "== Smoke /roles =="
curl -sS http://127.0.0.1:8001/roles | head -c 400 && echo
