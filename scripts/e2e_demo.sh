#!/usr/bin/env bash
set -e

API="${API_BASE:-http://localhost:8000}"
DOC_FILE="${1:-data/synthetic/demo_week9.docx}"
ROLE_ID="${ROLE_ID:-HKU.ROLE.ASSISTANT_PM.v1}"
SKILL_ID="${SKILL_ID:-HKU.SKILL.ACADEMIC_INTEGRITY.v1}"

# identities (dev RBAC headers)
H_ALICE=(-H "X-Subject-Id: alice" -H "X-Role: student")
H_OTHER=(-H "X-Subject-Id: student_other" -H "X-Role: student")
H_STAFF=(-H "X-Subject-Id: staff_demo" -H "X-Role: staff")
H_ADMIN=(-H "X-Subject-Id: admin_demo" -H "X-Role: admin")

echo "== Step 0: whoami =="
curl -s "$API/whoami" "${H_ALICE[@]}" | sed 's/.*/alice: &/'
curl -s "$API/whoami" "${H_STAFF[@]}" | sed 's/.*/staff: &/'
echo ""

echo "== Step 1: consent/start (alice) =="
START_JSON=$(curl -s -X POST "$API/consent/start" "${H_ALICE[@]}" -H "Content-Type: application/json" -d '{"scope":"analysis"}')
echo "$START_JSON"
DOC_ID=$(python3 - <<PY2
import json,sys
o=json.loads(sys.argv[1])
print(o["doc_id"])
PY2
"$START_JSON")
TOKEN=$(python3 - <<PY2
import json,sys
o=json.loads(sys.argv[1])
print(o["upload_token"])
PY2
"$START_JSON")
echo "DOC_ID=$DOC_ID"
echo "TOKEN=$TOKEN"
echo ""

echo "== Step 2: strict upload (alice) =="
if [ ! -f "$DOC_FILE" ]; then
  echo "ERROR: missing file $DOC_FILE"
  exit 1
fi
curl -s "${H_ALICE[@]}" \
  -F "doc_id=$DOC_ID" \
  -F "upload_token=$TOKEN" \
  -F "doc_type=synthetic" \
  -F "file=@$DOC_FILE" \
  "$API/documents/upload"
echo ""
echo ""

echo "== Step 3: chunks access checks =="
echo "-- alice (should 200)"
curl -s -i "${H_ALICE[@]}" "$API/documents/$DOC_ID/chunks?limit=1" | head -n 5
echo "-- other student (should 403)"
curl -s -i "${H_OTHER[@]}" "$API/documents/$DOC_ID/chunks?limit=1" | head -n 5
echo "-- staff (should 200)"
curl -s -i "${H_STAFF[@]}" "$API/documents/$DOC_ID/chunks?limit=1" | head -n 5
echo ""

echo "== Step 4: Decision 2 (alice) =="
curl -s -X POST "$API/assess/skill" "${H_ALICE[@]}" -H "Content-Type: application/json" \
  -d "{\"skill_id\":\"$SKILL_ID\",\"doc_id\":\"$DOC_ID\",\"k\":5,\"store\":false}" | python3 - <<'PY2'
import json,sys
o=json.load(sys.stdin)
print({"decision":o.get("decision"),"matched_terms":o.get("matched_terms"),"best_chunk":(o.get("best_evidence") or {}).get("idx")})
PY2
echo ""

echo "== Step 5: Decision 3 (alice) =="
curl -s -X POST "$API/assess/proficiency" "${H_ALICE[@]}" -H "Content-Type: application/json" \
  -d "{\"skill_id\":\"$SKILL_ID\",\"doc_id\":\"$DOC_ID\",\"k\":10,\"store\":false}" | python3 - <<'PY2'
import json,sys
o=json.load(sys.stdin)
print({"level":o.get("level"),"label":o.get("label"),"signals":o.get("signals")})
PY2
echo ""

echo "== Step 6: Decision 4 readiness (alice) =="
curl -s -X POST "$API/assess/role_readiness" "${H_ALICE[@]}" -H "Content-Type: application/json" \
  -d "{\"doc_id\":\"$DOC_ID\",\"role_id\":\"$ROLE_ID\",\"store\":false}" | python3 - <<'PY2'
import json,sys
o=json.load(sys.stdin)
print({"role_id":o.get("role_id"),"summary":o.get("summary")})
PY2
echo ""

echo "== Step 7: Decision 5 actions (alice) =="
curl -s -X POST "$API/actions/recommend" "${H_ALICE[@]}" -H "Content-Type: application/json" \
  -d "{\"doc_id\":\"$DOC_ID\",\"role_id\":\"$ROLE_ID\"}" | python3 - <<'PY2'
import json,sys
o=json.load(sys.stdin)
print({"summary":o.get("summary"),"n_action_cards":len(o.get("action_cards") or [])})
PY2
echo ""

echo "== Step 8: audit + changes (alice) =="
echo "-- audit (latest 3)"
curl -s "$API/audit?doc_id=$DOC_ID&limit=3" | python3 - <<'PY2'
import json,sys
o=json.load(sys.stdin)
items=o.get("items") or []
print([{"event":it.get("event_type"),"status":it.get("status_code")} for it in items])
PY2
echo "-- changes (latest 3)"
curl -s "$API/changes?doc_id=$DOC_ID&limit=3" | python3 - <<'PY2'
import json,sys
o=json.load(sys.stdin)
items=o.get("items") or []
print([{"object":it.get("object_type"),"key":it.get("key_text")} for it in items])
PY2
echo ""

echo "== Step 9: admin revoke (delete) =="
curl -s -i -X POST "$API/consent/revoke" "${H_ADMIN[@]}" -H "Content-Type: application/json" \
  -d "{\"doc_id\":\"$DOC_ID\",\"upload_token\":\"$TOKEN\",\"reason\":\"e2e demo cleanup\"}" | head -n 8
echo ""

echo "== Step 10: post-delete chunks should be 403/404 =="
curl -s -i "${H_ALICE[@]}" "$API/documents/$DOC_ID/chunks?limit=1" | head -n 8

echo ""
echo "DONE. Demo doc_id was: $DOC_ID"
