#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== 1) Backup main.py and roles router =="
ts="$(date +%Y%m%d%H%M%S)"
cp -f backend/app/main.py "backend/app/main.py.bak.${ts}" || true
cp -f backend/app/routers/roles.py "backend/app/routers/roles.py.bak.${ts}" || true

echo "== 2) Remove accidental duplicate include_router that can create /roles/roles =="
python3 - <<'PY'
from pathlib import Path
import re, sys

p = Path("backend/app/main.py")
s = p.read_text(encoding="utf-8")

# Common failure mode: include_router(roles_router, prefix="/roles") while roles_router already has @router.get("/roles")
# Another: include_router with prefix="/roles" AND router itself has prefix="/roles"
# We keep exactly ONE include_router for roles_router (prefer no prefix, because roles.py already defines /roles paths).
pat = r'^\s*app\.include_router\(\s*roles_router\s*(?:,\s*prefix\s*=\s*["\']\/roles["\']\s*)?(?:,\s*tags\s*=\s*\[[^\]]*\]\s*)?\)\s*$'
lines = s.splitlines(True)

hits = [i for i,l in enumerate(lines) if re.search(pat,l)]
if not hits:
    print("⚠️  No include_router(roles_router ...) line matched. Skipping remove step.")
else:
    # Keep the FIRST include_router(roles_router...) but rewrite it to no prefix (safe).
    keep = hits[0]
    for idx in reversed(hits):
        if idx == keep:
            continue
        lines.pop(idx)
    # normalize the kept line
    lines[keep] = "app.include_router(roles_router)\n"
    s2 = "".join(lines)
    p.write_text(s2, encoding="utf-8")
    print(f"✅ Normalized roles_router include_router to avoid /roles/roles. kept line {keep+1}, removed {len(hits)-1} dup(s).")
PY

echo "== 3) Restart uvicorn on :8001 (no reload) =="
mkdir -p logs
lsof -ti tcp:8001 | xargs -r kill -9 || true
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight}"
nohup uvicorn backend.app.main:app --port 8001 > logs/uvicorn_8001.log 2>&1 &
sleep 1

echo "== 4) Verify routes (expect NO /roles/roles) =="
curl -sS http://127.0.0.1:8001/__routes | python3 -c 'import json,sys; r=json.load(sys.stdin); paths=[x["path"] for x in r]; 
print("has_/roles/roles =", ("/roles/roles" in paths));
print("roles_like =", [p for p in paths if p.startswith("/roles")])'

echo
echo "== 5) Smoke =="
curl -sS http://127.0.0.1:8001/health; echo
curl -sS http://127.0.0.1:8001/roles | head -c 400; echo
curl -sS "http://127.0.0.1:8001/skills?q=HKU" | head -c 400; echo
echo "✅ cleanup done"
