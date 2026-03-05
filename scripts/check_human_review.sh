#!/usr/bin/env bash
# P5 Protocol 4: Human Review closed-loop verification
#
# 1. Get staff token
# 2. List review queue for COMP3000
# 3. Resolve one ticket (approve)
# 4. Verify change_log_events has human_review_resolved
#
# Bash 3.2 compatible. Exit non-zero on failure.
# Output to LOGS/check_human_review.log if LOGS env set.

set -e
set -u

API_BASE="${1:-http://127.0.0.1:8001}"
DB_PORT="${2:-55432}"
LOG_DIR="${LOGS:-}"
LOG_FILE=""
if [ -n "$LOG_DIR" ]; then
  mkdir -p "$LOG_DIR"
  LOG_FILE="$LOG_DIR/check_human_review.log"
fi

exec 3>&1
if [ -n "$LOG_FILE" ]; then
  exec 1>"$LOG_FILE" 2>&1
fi

echo "=== P5 check_human_review: $API_BASE DB=$DB_PORT ==="

# 1. Staff login
STAFF_RESP=$(curl -s -X POST "$API_BASE/bff/staff/auth/dev_login" \
  -H "Content-Type: application/json" \
  -d '{"subject_id":"staff_demo","role":"staff","course_ids":["COMP3000","COMP3100"],"term_id":"2025-26-T1"}')
STAFF_TOKEN=$(echo "$STAFF_RESP" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
if [ -z "$STAFF_TOKEN" ]; then
  echo "[FAIL] Could not get staff token"
  echo "Response: $STAFF_RESP"
  exit 1
fi
echo "[PASS] Staff login OK"

# 2. List review queue
QUEUE=$(curl -s -X GET "$API_BASE/bff/staff/courses/COMP3000/review_queue" \
  -H "Authorization: Bearer $STAFF_TOKEN" \
  -H "X-Purpose: teaching_support")
COUNT=$(echo "$QUEUE" | grep -o '"count":[0-9]*' | cut -d':' -f2)
if [ -z "$COUNT" ] || [ "$COUNT" -lt 1 ]; then
  echo "[WARN] No open tickets in COMP3000 queue (run seed_p3 first)"
  # Not fatal - resolve step will be skipped
  TICKET_ID=""
else
  TICKET_ID=$(echo "$QUEUE" | grep -o '"ticket_id":"[^"]*"' | head -1 | cut -d'"' -f4)
  echo "[PASS] Review queue has $COUNT tickets"
fi

# 3. Resolve one ticket if we have one
if [ -n "$TICKET_ID" ]; then
  RESOLVE=$(curl -s -w "\n%{http_code}" -X POST "$API_BASE/bff/staff/review/$TICKET_ID/resolve" \
    -H "Authorization: Bearer $STAFF_TOKEN" \
    -H "Content-Type: application/json" \
    -H "X-Purpose: teaching_support" \
    -d '{"decision":"approve","comment":"P5 verification"}')
  HTTP_CODE=$(echo "$RESOLVE" | tail -1)
  if [ "$HTTP_CODE" != "200" ]; then
    echo "[FAIL] Resolve returned HTTP $HTTP_CODE"
    echo "$RESOLVE"
    exit 1
  fi
  echo "[PASS] Resolved ticket $TICKET_ID"
else
  echo "[SKIP] No ticket to resolve"
fi

# 4. Verify change_log_events has human_review_resolved (if we resolved one)
if [ -n "$TICKET_ID" ]; then
  EVENTS=$(PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A \
    -c "SELECT COUNT(*) FROM change_log_events WHERE event_type='human_review_resolved' AND created_at > now() - interval '5 minutes';" 2>/dev/null || echo "0")
  if [ -z "$EVENTS" ] || [ "${EVENTS:-0}" -lt 1 ]; then
    echo "[FAIL] No human_review_resolved in change_log_events (expected >=1)"
    exit 1
  fi
  echo "[PASS] change_log_events has human_review_resolved"
fi

echo ""
echo "[PASS] check_human_review complete"
exit 0
