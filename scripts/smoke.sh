#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Health =="
curl -s http://localhost:8000/health | cat
echo

echo "== Week10-12 tests =="
bash ./scripts/test_week10_12.sh

echo "== Week8 async job smoke =="
DOC_ID=$(docker exec -i skillsight_db psql -U skillsight -d skillsight -t -A -c "select doc_id::text from consents where status='granted' order by created_at desc limit 1;")
DOC_ID=$(echo "$DOC_ID" | tr -d '[:space:]')
echo "DOC_ID=$DOC_ID"

RESP=$(curl -s -X POST http://localhost:8000/db/jobs/enqueue -H "Content-Type: application/json" -H "X-Subject-Id: staff_demo" -H "X-Role: staff" -d "{"doc_id":"$DOC_ID"}")
echo "$RESP"

sleep 2
curl -s "http://localhost:8000/db/jobs?doc_id=$DOC_ID&limit=3" -H "X-Subject-Id: staff_demo" -H "X-Role: staff" | cat
echo

echo "OK: smoke passed"
