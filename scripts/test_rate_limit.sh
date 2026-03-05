#!/usr/bin/env bash
# Demonstrate rate limiting: with RATE_LIMIT_ENABLED=1/true/yes/on and low limit, expect 429 after N requests.
# Usage: API must be running with RATE_LIMIT_ENABLED set in its env (start backend with it).
# Example: RATE_LIMIT_ENABLED=1 RATE_LIMIT_PER_MINUTE_AUTH=2 ./scripts/test_rate_limit.sh
set -euo pipefail

API_BASE="${1:-http://127.0.0.1:8001}"
# Use limit 2 for auth: 1st and 2nd = 200, 3rd+ = 429. Send 5 requests to guarantee at least one 429.
LIMIT="${RATE_LIMIT_PER_MINUTE_AUTH:-2}"
ENABLED="${RATE_LIMIT_ENABLED:-1}"

echo "=== Rate limit test ==="
echo "API_BASE=$API_BASE RATE_LIMIT_ENABLED=$ENABLED RATE_LIMIT_PER_MINUTE_AUTH=$LIMIT"
echo ""

# Truthy: 1, true, yes, on (case-insensitive); tr for bash 3.2 compat (no ${var,,})
enabled_lc="$(printf '%s' "${ENABLED:-}" | tr '[:upper:]' '[:lower:]')"
case "$enabled_lc" in
  1|true|yes|on) RATE_LIMIT_ACTIVE=1 ;;
  *) RATE_LIMIT_ACTIVE=0 ;;
esac

if [ "$RATE_LIMIT_ACTIVE" -eq 0 ]; then
  echo "RATE_LIMIT_ENABLED is not 1/true/yes/on; rate limiting disabled."
  echo "Making 2 requests to show they succeed:"
  for i in 1 2; do
    code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/auth/dev_login" -H "Content-Type: application/json" -d '{"subject_id":"rl_test","role":"student","ttl_s":60}')
    echo "  Request $i: HTTP $code"
  done
  echo "PASS (rate limit disabled)"
  exit 0
fi

# With limit N, first N = 200, (N+1)th = 429. Send 5 requests quickly.
got_429=0
for i in 1 2 3 4 5; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/auth/dev_login" -H "Content-Type: application/json" -d '{"subject_id":"rl_test","role":"student","ttl_s":60}')
  echo "  Request $i: HTTP $code"
  if [ "$code" = "429" ]; then
    got_429=1
  fi
done

if [ "$got_429" -eq 1 ]; then
  echo "PASS: received HTTP 429 after exceeding limit"
  exit 0
else
  echo "FAIL: no HTTP 429 observed in 5 requests (backend may not have RATE_LIMIT_ENABLED set or limit too high)"
  exit 1
fi
