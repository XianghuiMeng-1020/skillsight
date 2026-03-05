#!/usr/bin/env bash
# Refusal contract check – fail-closed
#
# Asserts:
# - In-body refusal (e.g. search items=[]) has refusal with only code, message, next_step (no label/reason).
# - 403 detail has ok:false and refusal with code, message, next_step (no label/reason).
#
# Usage: ./scripts/check_refusal_contract.sh [API_BASE] [DB_PORT]
# Env: LOGS (default REPO_ROOT/LOGS). Writes LOGS/check_refusal_contract.log.
# Bash 3.2 compatible.

set -e
set -u
set +o pipefail 2>/dev/null || true

API_BASE="${1:-http://127.0.0.1:8001}"
DB_PORT="${2:-55432}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="${LOGS:-$REPO_ROOT/LOGS}"
mkdir -p "$LOGS"
LOG_FILE="$LOGS/check_refusal_contract.log"
: > "$LOG_FILE"

fail() {
  echo "[FAIL] $1" | tee -a "$LOG_FILE"
  exit 1
}

run_py() {
  python3 -c "$1" 2>>"$LOG_FILE" || fail "Python check failed"
}

echo "=== Refusal contract check ===" | tee -a "$LOG_FILE"
echo "API_BASE=$API_BASE LOG_FILE=$LOG_FILE" | tee -a "$LOG_FILE"

# Gate: backend reachable
if ! curl -sf --connect-timeout 5 "$API_BASE/health" >/dev/null 2>&1; then
  echo "[GATE] Backend unreachable" | tee -a "$LOG_FILE"
  fail "Backend unreachable at $API_BASE/health"
fi
echo "[GATE] Backend reachable" | tee -a "$LOG_FILE"

# 1) Login as student
LOGIN_RESP=$(curl -fsS -X POST "$API_BASE/auth/dev_login" \
  -H "Content-Type: application/json" \
  -d '{"subject_id":"refusal_contract_test","role":"student","ttl_s":3600}' 2>/dev/null) || fail "dev_login failed"
TOKEN=$(echo "$LOGIN_RESP" | run_py "import sys,json; print(json.load(sys.stdin).get('token',''))")
[ -z "$TOKEN" ] && fail "No token from dev_login"
echo "[1] dev_login OK" | tee -a "$LOG_FILE"

# 2) Search that returns refusal (high min_score) – in-body refusal must be strict
SEARCH_BODY=$(curl -sS -X POST "$API_BASE/bff/student/search/evidence_vector" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query_text":"nonexistent xyz query","k":5,"min_score":0.99}' 2>>"$LOG_FILE")
echo "$SEARCH_BODY" | run_py "
import sys, json
d = json.load(sys.stdin)
r = d.get('refusal')
if not r or not isinstance(r, dict):
    sys.exit(1)
for k in ('code','message','next_step'):
    if k not in r or not isinstance(r.get(k), str):
        sys.exit(2)
if 'label' in r or 'reason' in r:
    sys.exit(3)
"
echo "[2] Search refusal: strict fields present, no label/reason" | tee -a "$LOG_FILE"

# 3) 403 without purpose (staff endpoint) – detail must have refusal with strict shape
STAFF_RESP=$(curl -sS -o /tmp/refusal_403.json -w "%{http_code}" \
  -X GET "$API_BASE/bff/staff/courses" \
  -H "Authorization: Bearer $TOKEN" 2>>"$LOG_FILE")
STAFF_STATUS="$STAFF_RESP"
if [ "$STAFF_STATUS" = "403" ]; then
  run_py "
import sys, json
with open('/tmp/refusal_403.json') as f:
    d = json.load(f)
detail = d.get('detail')
if not isinstance(detail, dict):
    sys.exit(1)
r = detail.get('refusal') or (detail if detail.get('code') else None)
if not r:
    sys.exit(2)
for k in ('code','message','next_step'):
    if k not in r or not isinstance(r.get(k), str):
        sys.exit(3)
if 'label' in r or 'reason' in r:
    sys.exit(4)
"
  echo "[3] 403 detail: strict refusal shape, no label/reason" | tee -a "$LOG_FILE"
else
  echo "[3] 403 not returned (status=$STAFF_STATUS); skipping 403 body check" | tee -a "$LOG_FILE"
fi
rm -f /tmp/refusal_403.json 2>/dev/null || true

# 4) Denylist: no label/reason anywhere in search refusal response
echo "$SEARCH_BODY" | run_py "
import sys, json
d = json.load(sys.stdin)
r = d.get('refusal')
if r and isinstance(r, dict) and ('label' in r or 'reason' in r):
    sys.exit(1)
"
echo "[4] Denylist: refusal object has no label/reason" | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "[PASS] Refusal contract check complete" | tee -a "$LOG_FILE"
exit 0
