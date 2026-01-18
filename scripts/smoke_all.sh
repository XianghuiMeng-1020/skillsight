#!/usr/bin/env bash
set -euo pipefail
BASE="http://127.0.0.1:8001"

pp() { python3 -m json.tool; }

echo "== health ==";  curl -sS "$BASE/health" | pp; echo
echo "== stats ==";   curl -sS "$BASE/stats"  | pp; echo
echo "== schemas =="; curl -sS "$BASE/schemas/summary" | pp; echo

echo "== routes (roles/skills only) =="
curl -sS "$BASE/__routes" | python3 -c 'import json,sys; r=json.load(sys.stdin); ps=sorted([x["path"] for x in r]); print("\n".join([p for p in ps if p.startswith(("/roles","/skills"))]))'
echo

echo "== roles =="
curl -sS "$BASE/roles" | pp
echo

echo "== role_id =="
code=$(curl -sS -o /tmp/role_id.json -w "%{http_code}" "$BASE/roles/HKU.ROLE.ASSISTANT_PM.v1" || true)
echo "HTTP $code"
if [ "$code" = "200" ] && [ -s /tmp/role_id.json ]; then
  python3 -m json.tool < /tmp/role_id.json
else
  echo "-- body (first 400 bytes) --"
  head -c 400 /tmp/role_id.json 2>/dev/null || true
  echo
  echo "-- tail log --"
  tail -n 80 logs/uvicorn_8001.log 2>/dev/null || true
  exit 1
fi
echo

echo "== skills (q=HKU) =="
curl -sS "$BASE/skills?q=HKU" | pp
echo

echo "== openapi roles/skills paths =="
curl -sS "$BASE/openapi.json" | python3 -c 'import json,sys; o=json.load(sys.stdin); paths=sorted(o.get("paths",{})); print("\n".join([p for p in paths if p.startswith(("/roles","/skills"))]))'
echo

echo "✅ smoke_all ok"
