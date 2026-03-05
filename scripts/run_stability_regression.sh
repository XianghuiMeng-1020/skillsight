#!/usr/bin/env bash
# Stability regression: same content upload 10x → doc_id reuse; same role+doc readiness 10x → score consistent
# Usage: ./scripts/run_stability_regression.sh [API_BASE]
# Requires: backend running, DB seeded (roles exist)

set -e
API_BASE="${1:-http://127.0.0.1:8001}"
USER="stability_user_001"
ROLE_ID=""
DOC_ID=""

fail() { echo "[FAIL] $1"; exit 1; }
ok()   { echo "[OK]   $1"; }

echo "=== Stability Regression ==="
echo "API_BASE=$API_BASE"

# Gate
curl -sf --connect-timeout 5 "$API_BASE/health" >/dev/null || fail "Backend unreachable"

# Login
TOKEN=$(curl -fsS -X POST "$API_BASE/auth/dev_login" \
  -H "Content-Type: application/json" \
  -d "{\"subject_id\":\"$USER\",\"role\":\"student\",\"ttl_s\":3600}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
[ -z "$TOKEN" ] && fail "No token"
ok "Logged in"

# Get first role
ROLE_ID=$(curl -fsS "$API_BASE/roles?limit=1" | python3 -c "import sys,json; d=json.load(sys.stdin); r=d.get('roles',d.get('items',[])); print(r[0]['role_id'] if r else '')" 2>/dev/null)
[ -z "$ROLE_ID" ] && fail "No role - run seed first"
ok "role_id=$ROLE_ID"

# ─── Test 1: Same content upload 10x → doc_id stable ─────────────────────────
echo ""
echo "--- Test 1: Same content upload 10x (doc_id reuse) ---"
TEST_FILE=$(mktemp)
echo "Stable regression content: Python, pandas, data analysis. Unit tests." > "$TEST_FILE"
DOC_IDS=()
for i in $(seq 1 10); do
  R=$(curl -sS -X POST "$API_BASE/bff/student/documents/upload" \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@$TEST_FILE;filename=stable_$i.txt" \
    -F "purpose=skill_assessment" \
    -F "scope=full" \
    -w "\nHTTP:%{http_code}")
  STATUS=$(echo "$R" | awk -F: '/HTTP:/ {print $2}' | tr -d ' \r')
  BODY=$(echo "$R" | sed '/HTTP:/d')
  [ "$STATUS" != "200" ] && fail "Upload $i failed HTTP $STATUS: $BODY"
  DID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('doc_id',''))" 2>/dev/null)
  [ -z "$DID" ] && fail "Upload $i: no doc_id"
  DOC_IDS+=("$DID")
done
rm -f "$TEST_FILE"

UNIQUE=$(printf '%s\n' "${DOC_IDS[@]}" | sort -u | wc -l | tr -d ' ')
if [ "$UNIQUE" -eq 1 ]; then
  ok "10 uploads → 1 unique doc_id (stable reuse)"
else
  fail "10 uploads → $UNIQUE unique doc_ids (expected 1). IDs: ${DOC_IDS[*]}"
fi
DOC_ID="${DOC_IDS[0]}"
ok "doc_id=$DOC_ID"

# Embed (needed for readiness)
echo ""
echo "Embedding doc..."
curl -fsS -X POST "$API_BASE/bff/student/chunks/embed/$DOC_ID" \
  -H "Authorization: Bearer $TOKEN" >/dev/null || fail "Embed failed"
ok "Embedded"

# ─── Test 2: Same role+doc readiness 10x → score consistent ───────────────────
echo ""
echo "--- Test 2: Same role+doc readiness 10x (score stable) ---"
SCORES=()
SUMMARY_STRINGS=()
for i in $(seq 1 10); do
  R=$(curl -sS -X POST "$API_BASE/bff/student/roles/alignment" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"role_id\":\"$ROLE_ID\",\"doc_id\":\"$DOC_ID\"}" \
    -w "\nHTTP:%{http_code}")
  STATUS=$(echo "$R" | awk -F: '/HTTP:/ {print $2}' | tr -d ' \r')
  BODY=$(echo "$R" | sed '/HTTP:/d')
  [ "$STATUS" != "200" ] && fail "Readiness $i failed HTTP $STATUS: $BODY"
  S=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('score', d.get('readiness_score','')))" 2>/dev/null)
  SS=$(echo "$BODY" | python3 -c "
import sys,json
d=json.load(sys.stdin)
s=d.get('status_summary',{})
print(json.dumps(s,sort_keys=True))
" 2>/dev/null)
  SCORES+=("$S")
  SUMMARY_STRINGS+=("$SS")
done

UNIQUE_SCORES=$(printf '%s\n' "${SCORES[@]}" | sort -u | wc -l | tr -d ' ')
UNIQUE_SUMMARIES=$(printf '%s\n' "${SUMMARY_STRINGS[@]}" | sort -u | wc -l | tr -d ' ')
if [ "$UNIQUE_SCORES" -eq 1 ] && [ "$UNIQUE_SUMMARIES" -eq 1 ]; then
  ok "10 readiness calls → score=$SCORES, status_summary stable"
else
  fail "10 readiness → $UNIQUE_SCORES unique scores, $UNIQUE_SUMMARIES unique summaries. Scores: ${SCORES[*]}"
fi

echo ""
echo "=== All stability checks PASSED ==="
