#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Default config (can override by env)
API_BASE="${API_BASE:-http://127.0.0.1:8001}"
DB_URL="${DB_URL:-postgresql://skillsight:skillsight@localhost:55432/skillsight}"

echo "== config =="
echo "API_BASE=$API_BASE"
echo "DB_URL=$DB_URL"

echo
echo "== db ping =="
psql "$DB_URL" -c "select 1;" >/dev/null
echo "✅ db ok"

echo
echo "== api health =="
curl -fsS "${API_BASE}/health" >/dev/null
echo "✅ api ok"

echo
echo "== run audit (optional but recommended) =="
if [[ -x scripts/audit_skillsight_progress.sh ]]; then
  bash scripts/audit_skillsight_progress.sh >/dev/null
  LATEST="$(ls -1t reports/skillsight_audit_*.md 2>/dev/null | head -n 1 || true)"
  echo "✅ audit ok (latest: ${LATEST:-none})"
else
  echo "⚠️ scripts/audit_skillsight_progress.sh not found or not executable"
fi

echo
echo "== smoke endpoints =="
# Small helper
get_json_len () {
  local url="$1"
  curl -fsS "$url" | python3 -c 'import json,sys; d=json.load(sys.stdin); 
items = d.get("items") if isinstance(d,dict) else d
print(len(items) if isinstance(items,list) else (d.get("count") if isinstance(d,dict) else "na"))'
}

echo "✅ /skills count: $(get_json_len "${API_BASE}/skills?limit=5")"
echo "✅ /roles  count: $(get_json_len "${API_BASE}/roles?limit=5")"
echo "✅ /documents count: $(curl -fsS "${API_BASE}/documents?limit=5" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("count"))')"
echo "✅ /chunks count: $(get_json_len "${API_BASE}/chunks?limit=5")"
echo "✅ /consents count: $(get_json_len "${API_BASE}/consents")"
echo "✅ /jobs count: $(get_json_len "${API_BASE}/jobs?limit=5")"
echo "✅ /courses count: $(get_json_len "${API_BASE}/courses?limit=5")"
echo "✅ /course-skill-map count: $(curl -fsS "${API_BASE}/course-skill-map?limit=10" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("count"))')"

echo
echo "✅ GREEN: db+api+smoke ok"
