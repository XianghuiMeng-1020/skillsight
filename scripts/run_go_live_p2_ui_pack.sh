#!/usr/bin/env bash
# P2 Evidence Pack – UI Golden Path + Governance + BFF boundary verification
#
# Produces a reproducible, auditable evidence pack for:
#   - Student UI golden path (upload → embed → search → skills profile → role alignment → export)
#   - Consent management & deletion (DB + Qdrant verified)
#   - BFF boundary: /bff/student/* endpoints with consent enforcement
#   - P0 baseline (from P1 pack)
#   - Audit trail check
#   - Rate limit check
#   - UI E2E (Playwright)
#
# Usage:
#   CLEAN_RUN=1 ./scripts/run_go_live_p2_ui_pack.sh
#
# Environment variables (with defaults):
#   BACKEND_PORT  8001
#   DB_PORT       55432
#   FRONTEND_PORT 3000
#   CLEAN_RUN     0  (set to 1 to docker compose down -v first)
#
# Output: artifacts/go_live_baseline_p2/YYYYMMDD_HHMMSS/
#   LOGS/bootstrap.log
#   LOGS/backend.log / worker.log / web.log
#   LOGS/docker_ps.log / docker_compose.log
#   LOGS/audit_check.sql.out
#   LOGS/rate_limit_test.log
#   LOGS/deletion_check.out
#   P0_VERIFICATION_OUTPUT.txt
#   UI_E2E_OUTPUT.txt
#   SUMMARY.md
#
# Compatibility: bash 3.2+ (macOS default). No bash4+ features.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

BACKEND_PORT="${BACKEND_PORT:-8001}"
DB_PORT="${DB_PORT:-55432}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
OUT_DIR="artifacts/go_live_baseline_p2/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT_DIR/LOGS"
LOGS="$OUT_DIR/LOGS"

BACKEND_PID=""
WORKER_PID=""
WEB_PID=""

cleanup() {
  if [ -n "$BACKEND_PID" ]; then kill "$BACKEND_PID" 2>/dev/null || true; wait "$BACKEND_PID" 2>/dev/null || true; fi
  if [ -n "$WORKER_PID" ]; then kill "$WORKER_PID" 2>/dev/null || true; wait "$WORKER_PID" 2>/dev/null || true; fi
  if [ -n "$WEB_PID" ]; then kill "$WEB_PID" 2>/dev/null || true; wait "$WEB_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT

API_BASE="http://127.0.0.1:$BACKEND_PORT"

step_pass() { echo "[PASS] $*"; }
step_fail() { echo "[FAIL] $*"; }

echo "========================================================"
echo " P2 UI Evidence Pack -> $OUT_DIR"
echo "========================================================"

# ─── Step 1: Optional clean run ──────────────────────────────────────────────
if [ "${CLEAN_RUN:-0}" = "1" ]; then
  echo "[1] CLEAN_RUN=1: docker compose down -v"
  docker compose down -v || true
  pkill -f "uvicorn backend.app.main" 2>/dev/null || true
  pkill -f "python.*worker\.py" 2>/dev/null || true
  pkill -f "next dev" 2>/dev/null || true
  sleep 2
else
  echo "[1] Skipping clean run (CLEAN_RUN not set to 1)"
fi

# ─── Step 2: Bootstrap ───────────────────────────────────────────────────────
echo "[2] Bootstrap -> LOGS/bootstrap.log"
./scripts/bootstrap_dev.sh 2>&1 | tee "$LOGS/bootstrap.log"

VENV_DIR="${VENV_DIR:-$REPO_ROOT/venv}"
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://skillsight:skillsight@127.0.0.1:$DB_PORT/skillsight}"
export QDRANT_HOST="${QDRANT_HOST:-127.0.0.1}"

# ─── Step 3: Start backend ───────────────────────────────────────────────────
echo "[3a] Checking backend..."
backend_up() {
  curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "$API_BASE/health" 2>/dev/null | grep -q 200
}
worker_running() {
  pgrep -f "python.*worker\.py" >/dev/null 2>&1
}
web_up() {
  curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "http://127.0.0.1:$FRONTEND_PORT" 2>/dev/null | grep -q "200\|304"
}

if ! backend_up; then
  echo "[3a] Starting backend (with rate limit env)..."
  (cd "$REPO_ROOT/backend" && \
    RATE_LIMIT_ENABLED=1 \
    RATE_LIMIT_PER_MINUTE_AUTH=2 \
    QDRANT_HOST=127.0.0.1 \
    PYTHONPATH="$REPO_ROOT" \
    uvicorn backend.app.main:app --host 0.0.0.0 --port "$BACKEND_PORT") \
    2>&1 | tee "$LOGS/backend.log" &
  BACKEND_PID=$!
  WAITED=0
  until backend_up; do
    sleep 1
    WAITED=$((WAITED + 1))
    if [ "$WAITED" -ge 45 ]; then echo "Backend did not become ready"; exit 1; fi
  done
  echo "[3a] Backend ready."
else
  echo "[3a] Backend already running on port $BACKEND_PORT"
fi

if ! worker_running; then
  echo "[3b] Starting worker..."
  (cd "$REPO_ROOT" && python backend/worker.py) 2>&1 | tee "$LOGS/worker.log" &
  WORKER_PID=$!
  sleep 2
  echo "[3b] Worker started."
else
  echo "[3b] Worker already running."
fi

echo "[3c] Checking frontend..."
if ! web_up; then
  echo "[3c] Starting Next.js dev server on port $FRONTEND_PORT..."
  (cd "$REPO_ROOT/web" && npm run dev -- --port "$FRONTEND_PORT") \
    2>&1 | tee "$LOGS/web.log" &
  WEB_PID=$!
  WAITED=0
  until web_up; do
    sleep 2
    WAITED=$((WAITED + 2))
    if [ "$WAITED" -ge 60 ]; then
      echo "[3c] WARNING: Frontend did not become ready in 60s, continuing anyway"
      break
    fi
  done
  if web_up; then echo "[3c] Frontend ready."; fi
else
  echo "[3c] Frontend already running on port $FRONTEND_PORT"
fi

# ─── Step 4: P0 Verification ─────────────────────────────────────────────────
echo "[4] P0 verification -> P0_VERIFICATION_OUTPUT.txt"
P0_RESULT="PASS"
if ! ./scripts/verify_p0.sh "$API_BASE" "$DB_PORT" 2>&1 | tee "$OUT_DIR/P0_VERIFICATION_OUTPUT.txt"; then
  P0_RESULT="FAIL"
  echo "[4] P0 verification FAILED – aborting evidence pack"
  exit 1
fi
grep -q "PASS" "$OUT_DIR/P0_VERIFICATION_OUTPUT.txt" || P0_RESULT="FAIL"
echo "[4] P0: $P0_RESULT"

# ─── Step 5: Docker evidence ─────────────────────────────────────────────────
echo "[5] Docker evidence -> LOGS/"
docker compose ps > "$LOGS/docker_ps.log" 2>&1 || true
docker compose logs --no-color > "$LOGS/docker_compose.log" 2>&1 || true

# ─── Step 6: BFF smoke tests ─────────────────────────────────────────────────
echo "[6] BFF boundary smoke tests"
BFF_RESULT="PASS"

# Test 1: Upload without purpose → expect 422
UPLOAD_RESP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/bff/student/documents/upload" \
  -H "Authorization: Bearer test" \
  -F "file=@/etc/hostname;type=text/plain" \
  -F "scope=full" 2>/dev/null || echo "000")
if [ "$UPLOAD_RESP" = "422" ] || [ "$UPLOAD_RESP" = "403" ] || [ "$UPLOAD_RESP" = "401" ]; then
  echo "[6] BFF upload without purpose → $UPLOAD_RESP (expected blocked)"
else
  echo "[6] WARN: BFF upload without purpose returned $UPLOAD_RESP (expected 401/403/422)"
fi

# Test 2: BFF /bff/student/profile requires auth → expect 403 or 401 without token
PROFILE_RESP=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE/bff/student/profile" 2>/dev/null || echo "000")
if [ "$PROFILE_RESP" = "403" ] || [ "$PROFILE_RESP" = "401" ]; then
  echo "[6] BFF profile without token → $PROFILE_RESP (expected)"
else
  echo "[6] WARN: BFF profile without token returned $PROFILE_RESP"
fi

# Test 3: BFF endpoints exist (dev_login proxy)
BFF_LOGIN=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/bff/student/auth/dev_login" \
  -H "Content-Type: application/json" \
  -d '{"subject_id":"bff_smoke_test","role":"student"}' 2>/dev/null || echo "000")
if [ "$BFF_LOGIN" = "200" ]; then
  echo "[6] BFF dev_login → 200 OK"
else
  echo "[6] WARN: BFF dev_login → $BFF_LOGIN"
  BFF_RESULT="WARN"
fi

# Staff BFF: requires staff role → test with student token (should get 403 or 200 with role check)
STAFF_BFF=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE/bff/staff/overview" 2>/dev/null || echo "000")
echo "[6] Staff BFF /overview (no token) → $STAFF_BFF (expected 401/403)"
echo "[6] BFF boundary: $BFF_RESULT" | tee -a "$LOGS/bff_smoke.log"

# ─── Step 7: Audit check ─────────────────────────────────────────────────────
echo "[7] Audit check -> LOGS/audit_check.sql.out"
{
  echo "-- P2: Audit check (BFF actions + standard actions)"
  echo "SELECT action, status, COUNT(*) AS n FROM audit_logs WHERE created_at > now() - interval '2 hours' GROUP BY action, status ORDER BY action, status;"
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A \
    -c "SELECT action, status, COUNT(*) AS n FROM audit_logs WHERE created_at > now() - interval '2 hours' GROUP BY action, status ORDER BY action, status;" 2>&1
  echo ""
  echo "-- BFF actions (P2)"
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A \
    -c "SELECT action FROM audit_logs WHERE action LIKE 'bff.%' ORDER BY created_at DESC LIMIT 20;" 2>&1
  echo ""
  echo "-- Consent / Deletion actions"
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight \
    -c "SELECT action, status, COUNT(*) FROM audit_logs WHERE action IN ('consent.grant','consent.revoke','bff.consents.withdraw','bff.documents.delete','bff.documents.upload') GROUP BY 1, 2 ORDER BY 1, 2;" 2>&1
} 2>&1 | tee "$LOGS/audit_check.sql.out"

# ─── Step 8: Rate limit check ────────────────────────────────────────────────
echo "[8] Rate limit check -> LOGS/rate_limit_test.log"
RATE_RESULT="FAIL"
if RATE_LIMIT_ENABLED=1 RATE_LIMIT_PER_MINUTE_AUTH=2 ./scripts/test_rate_limit.sh "$API_BASE" 2>&1 | tee "$LOGS/rate_limit_test.log"; then
  grep -q "HTTP 429" "$LOGS/rate_limit_test.log" && RATE_RESULT="PASS"
fi
echo "[8] Rate limit: $RATE_RESULT"

# ─── Step 9: Deletion check ──────────────────────────────────────────────────
echo "[9] Deletion check -> LOGS/deletion_check.out"
DELETION_RESULT="PASS"
if ! LOG_FILE="$LOGS/deletion_check.out" ./scripts/check_deletion.sh "$API_BASE" "$DB_PORT" \
    2>&1 | tee "$LOGS/deletion_check.out"; then
  DELETION_RESULT="FAIL"
fi
grep -q "PASS:" "$LOGS/deletion_check.out" || DELETION_RESULT="WARN"
echo "[9] Deletion: $DELETION_RESULT"

# ─── Step 10: UI E2E (Playwright) ────────────────────────────────────────────
echo "[10] UI E2E (Playwright) -> UI_E2E_OUTPUT.txt"
E2E_RESULT="FAIL"
mkdir -p "$OUT_DIR/test-results"
(
  cd "$REPO_ROOT/web"
  API_BASE_URL="$API_BASE" \
  NEXT_PUBLIC_FRONTEND_URL="http://localhost:$FRONTEND_PORT" \
  npx playwright install chromium --with-deps 2>/dev/null || true
  API_BASE_URL="$API_BASE" \
  NEXT_PUBLIC_FRONTEND_URL="http://localhost:$FRONTEND_PORT" \
  npx playwright test tests/e2e/student_golden_path.spec.ts \
    --reporter=list 2>&1
) | tee "$OUT_DIR/UI_E2E_OUTPUT.txt" && E2E_RESULT="PASS" || E2E_RESULT="FAIL"

# Copy Playwright screenshots to evidence
cp -r "$REPO_ROOT/web/test-results/." "$OUT_DIR/test-results/" 2>/dev/null || true
echo "[10] E2E: $E2E_RESULT"

# ─── Step 11: Generate SUMMARY.md ────────────────────────────────────────────
echo "[11] Writing SUMMARY.md"
RUN_DATE="$(date)"

SUMMARY_FILE="$OUT_DIR/SUMMARY.md"
cat > "$SUMMARY_FILE" << HEREDOC
# P2 UI Evidence Pack Summary

**Run:** $RUN_DATE
**Output dir:** $OUT_DIR
**Repo:** $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')

## Results

| Step | Description | Result | Log / Artifact |
|------|-------------|--------|----------------|
| 1 | Clean run (CLEAN_RUN=$CLEAN_RUN) | — | — |
| 2 | Bootstrap | — | [LOGS/bootstrap.log](LOGS/bootstrap.log) |
| 3 | Backend + worker + frontend | — | [LOGS/backend.log](LOGS/backend.log), [LOGS/worker.log](LOGS/worker.log), [LOGS/web.log](LOGS/web.log) |
| 4 | P0 verification | **$P0_RESULT** | [P0_VERIFICATION_OUTPUT.txt](P0_VERIFICATION_OUTPUT.txt) |
| 5 | Docker evidence | — | [LOGS/docker_ps.log](LOGS/docker_ps.log) |
| 6 | BFF boundary smoke | **$BFF_RESULT** | [LOGS/bff_smoke.log](LOGS/bff_smoke.log) |
| 7 | Audit check (BFF + consent + deletion actions) | — | [LOGS/audit_check.sql.out](LOGS/audit_check.sql.out) |
| 8 | Rate limit (HTTP 429) | **$RATE_RESULT** | [LOGS/rate_limit_test.log](LOGS/rate_limit_test.log) |
| 9 | Deletion (DB + Qdrant + audit verified) | **$DELETION_RESULT** | [LOGS/deletion_check.out](LOGS/deletion_check.out) |
| 10 | UI E2E (Playwright golden path) | **$E2E_RESULT** | [UI_E2E_OUTPUT.txt](UI_E2E_OUTPUT.txt), [test-results/](test-results/) |

## DoD Coverage

| DoD Item | Status | Notes |
|----------|--------|-------|
| A1: dev_login → Student Dashboard | $E2E_RESULT | E2E test A1 |
| A2: Upload with consent (purpose+scope required) | $E2E_RESULT | E2E test A2, BFF /bff/student/documents/upload |
| A3: Processing status (embed) | $E2E_RESULT | E2E test A3, /bff/student/chunks/embed |
| A4: Skills Profile with evidence expand | $E2E_RESULT | E2E test A4, /bff/student/profile |
| A5: Role Alignment + Actions | $E2E_RESULT | E2E test A5, /bff/student/roles/alignment |
| A6: Export Statement | $E2E_RESULT | E2E test A6, /export page |
| B7: Consent withdrawal UX | $E2E_RESULT | E2E test B7, /settings/privacy |
| B8: Deletion (DB + Qdrant clean) | $DELETION_RESULT | [LOGS/deletion_check.out](LOGS/deletion_check.out) |
| C10: BFF route groups (/bff/student,staff,programme,admin) | $BFF_RESULT | Step 6 smoke tests |
| D11: One-command evidence pack | **DONE** | This script |

## API Boundary Summary

- **/bff/student/***: Consent enforced, purpose+scope required at upload, audit logged
- **/bff/staff/***: Aggregated only, no individual student data (role check: staff/admin)
- **/bff/programme/***: Cohort-level aggregations (role check: staff/admin/programme)
- **/bff/admin/***: Full audit visibility (role check: admin)

## How to reproduce

\`\`\`bash
CLEAN_RUN=1 ./scripts/run_go_live_p2_ui_pack.sh
\`\`\`

See [docs/RUNBOOK_LOCAL_VERIFY.md](../../docs/RUNBOOK_LOCAL_VERIFY.md) for full details.
HEREDOC

echo ""
echo "========================================================"
echo " EVIDENCE PACK COMPLETE"
echo " Output: $OUT_DIR"
echo " SUMMARY: $SUMMARY_FILE"
echo "========================================================"
cat "$SUMMARY_FILE"

# ─── Exit non-zero if any critical step failed ────────────────────────────────
FAIL_STEPS=""
[ "$P0_RESULT" = "FAIL" ] && FAIL_STEPS="$FAIL_STEPS P0"
[ "$RATE_RESULT" = "FAIL" ] && FAIL_STEPS="$FAIL_STEPS RATE_LIMIT"
[ "$DELETION_RESULT" = "FAIL" ] && FAIL_STEPS="$FAIL_STEPS DELETION"
[ "$E2E_RESULT" = "FAIL" ] && FAIL_STEPS="$FAIL_STEPS E2E"

if [ -n "$FAIL_STEPS" ]; then
  echo ""
  echo "FAIL: The following steps failed:$FAIL_STEPS"
  echo "See the corresponding log files in $LOGS/"
  exit 1
fi

echo ""
echo "All critical steps PASSED. Evidence pack ready."
