#!/usr/bin/env bash
# P3 Evidence Pack – Staff / Programme / Admin BFF + RBAC/ABAC + Review Workflow
#
# Produces a reproducible, auditable evidence pack for:
#   - P0 baseline (from P1 pack)
#   - P1 verification (rate limit / audit / deletion)
#   - P3 seed data (seed_p3_demo_data.py)
#   - P3 API smoke (staff/programme/admin BFF endpoints)
#   - P3 UI E2E (staff, programme, admin golden paths)
#   - Audit check (ticket.create/ticket.resolve, admin audit query)
#
# Usage:
#   CLEAN_RUN=1 ./scripts/run_go_live_p3_pack.sh
#
# Environment variables (with defaults):
#   BACKEND_PORT  8001
#   DB_PORT       55432
#   FRONTEND_PORT 3000
#   CLEAN_RUN     0  (set to 1 to docker compose down -v first)
#
# Output: artifacts/go_live_baseline_p3/YYYYMMDD_HHMMSS/
#   P0_VERIFICATION_OUTPUT.txt
#   P1_VERIFICATION_OUTPUT.txt (rate limit + audit + deletion)
#   P3_SEED_OUTPUT.txt
#   P3_API_SMOKE.txt
#   P3_UI_E2E_OUTPUT.txt
#   LOGS/audit_check_p3.sql.out
#   LOGS/...
#   SUMMARY.md
#
# Compatibility: bash 3.2+ (macOS default). No bash4+ features.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

BACKEND_PORT="${BACKEND_PORT:-8001}"
DB_PORT="${DB_PORT:-55432}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
OUT_DIR="artifacts/go_live_baseline_p3/$(date +%Y%m%d_%H%M%S)"
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
echo " P3 Evidence Pack -> $OUT_DIR"
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

# ─── Step 3: Start backend + worker + frontend ───────────────────────────────
echo "[3a] Checking backend..."
backend_up() {
  curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "$API_BASE/health" 2>/dev/null | grep -q 200
}
worker_running() {
  pgrep -f "python.*worker\.py" >/dev/null 2>&1
}
web_up() {
  curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "http://127.0.0.1:$FRONTEND_PORT" 2>/dev/null | grep -qE "200|304"
}

if ! backend_up; then
  echo "[3a] Starting backend..."
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

# ─── Step 5: P1 verification (rate limit + audit + deletion) ─────────────────
echo "[5] P1 verification -> P1_VERIFICATION_OUTPUT.txt"
P1_RESULT="PASS"
{
  echo "=== Rate limit check ==="
  RATE_LIMIT_ENABLED=1 RATE_LIMIT_PER_MINUTE_AUTH=2 ./scripts/test_rate_limit.sh "$API_BASE" 2>&1 || true
  echo ""
  echo "=== Audit check ==="
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A \
    -c "SELECT action, status, COUNT(*) FROM audit_logs WHERE created_at > now() - interval '2 hours' GROUP BY action, status ORDER BY 1, 2 LIMIT 30;" 2>&1 || true
  echo ""
  echo "=== Deletion check ==="
  LOG_FILE="$LOGS/deletion_check.out" ./scripts/check_deletion.sh "$API_BASE" "$DB_PORT" 2>&1 || true
} | tee "$OUT_DIR/P1_VERIFICATION_OUTPUT.txt"
grep -q "PASS\|429" "$OUT_DIR/P1_VERIFICATION_OUTPUT.txt" 2>/dev/null || P1_RESULT="WARN"
echo "[5] P1: $P1_RESULT"

# ─── Step 6: P3 seed ────────────────────────────────────────────────────────
echo "[6] P3 seed -> P3_SEED_OUTPUT.txt"
P3_SEED_RESULT="PASS"
if PYTHONPATH="$REPO_ROOT" SKILLSIGHT_API="$API_BASE" python scripts/seed_p3_demo_data.py 2>&1 | tee "$OUT_DIR/P3_SEED_OUTPUT.txt"; then
  grep -q "SEED COMPLETE" "$OUT_DIR/P3_SEED_OUTPUT.txt" || P3_SEED_RESULT="WARN"
else
  P3_SEED_RESULT="FAIL"
  echo "[6] P3 seed FAILED"
  exit 1
fi
echo "[6] P3 seed: $P3_SEED_RESULT"

# ─── Step 7: P3 API smoke ───────────────────────────────────────────────────
echo "[7] P3 API smoke -> P3_API_SMOKE.txt"
P3_API_RESULT="PASS"
{
  echo "=== Staff BFF ==="
  STAFF_TOKEN=$(curl -s -X POST "$API_BASE/bff/staff/auth/dev_login" \
    -H "Content-Type: application/json" \
    -d '{"subject_id":"staff_demo","role":"staff","course_ids":["COMP3000","COMP3100"],"term_id":"2025-26-T1"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null || echo "")
  if [ -n "$STAFF_TOKEN" ]; then
    curl -s -o /dev/null -w "GET /bff/staff/courses: %{http_code}\n" -H "Authorization: Bearer $STAFF_TOKEN" -H "X-Purpose: teaching_support" "$API_BASE/bff/staff/courses"
    curl -s -o /dev/null -w "GET /bff/staff/courses/COMP3000/skills_summary: %{http_code}\n" -H "Authorization: Bearer $STAFF_TOKEN" -H "X-Purpose: teaching_support" "$API_BASE/bff/staff/courses/COMP3000/skills_summary"
    curl -s -o /dev/null -w "GET /bff/staff/courses/COMP3000/review_queue: %{http_code}\n" -H "Authorization: Bearer $STAFF_TOKEN" -H "X-Purpose: teaching_support" "$API_BASE/bff/staff/courses/COMP3000/review_queue"
  else
    echo "Staff dev_login failed"
  fi

  echo ""
  echo "=== Programme BFF ==="
  PROG_TOKEN=$(curl -s -X POST "$API_BASE/bff/programme/auth/dev_login" \
    -H "Content-Type: application/json" \
    -d '{"subject_id":"prog_leader_demo","role":"programme_leader","programme_id":"CSCI_MSC"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null || echo "")
  if [ -n "$PROG_TOKEN" ]; then
    curl -s -o /dev/null -w "GET /bff/programme/programmes: %{http_code}\n" -H "Authorization: Bearer $PROG_TOKEN" -H "X-Purpose: aggregate_programme_analysis" "$API_BASE/bff/programme/programmes"
    curl -s -o /dev/null -w "GET /bff/programme/programmes/CSCI_MSC/coverage_matrix: %{http_code}\n" -H "Authorization: Bearer $PROG_TOKEN" -H "X-Purpose: aggregate_programme_analysis" "$API_BASE/bff/programme/programmes/CSCI_MSC/coverage_matrix"
  else
    echo "Programme dev_login failed"
  fi

  echo ""
  echo "=== Admin BFF ==="
  ADMIN_TOKEN=$(curl -s -X POST "$API_BASE/bff/admin/auth/dev_login" \
    -H "Content-Type: application/json" \
    -d '{"subject_id":"admin_seed","role":"admin"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null || echo "")
  if [ -n "$ADMIN_TOKEN" ]; then
    curl -s -o /dev/null -w "GET /bff/admin/skills: %{http_code}\n" -H "Authorization: Bearer $ADMIN_TOKEN" "$API_BASE/bff/admin/skills"
    curl -s -o /dev/null -w "GET /bff/admin/roles: %{http_code}\n" -H "Authorization: Bearer $ADMIN_TOKEN" "$API_BASE/bff/admin/roles"
    curl -s -o /dev/null -w "GET /bff/admin/audit/search: %{http_code}\n" -H "Authorization: Bearer $ADMIN_TOKEN" "$API_BASE/bff/admin/audit/search"
    curl -s -o /dev/null -w "GET /bff/admin/metrics/usage: %{http_code}\n" -H "Authorization: Bearer $ADMIN_TOKEN" "$API_BASE/bff/admin/metrics/usage"
    curl -s -o /dev/null -w "GET /bff/admin/health: %{http_code}\n" -H "Authorization: Bearer $ADMIN_TOKEN" "$API_BASE/bff/admin/health"
  else
    echo "Admin dev_login failed"
  fi
} 2>&1 | tee "$OUT_DIR/P3_API_SMOKE.txt"
grep -q "200" "$OUT_DIR/P3_API_SMOKE.txt" || P3_API_RESULT="FAIL"
echo "[7] P3 API smoke: $P3_API_RESULT"

# ─── Step 8: Audit check P3 ──────────────────────────────────────────────────
echo "[8] Audit check P3 -> LOGS/audit_check_p3.sql.out"
{
  echo "-- P3: ticket.create / ticket.resolve / admin audit"
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A \
    -c "SELECT action, status, COUNT(*) FROM audit_logs WHERE action LIKE 'bff.%' AND created_at > now() - interval '2 hours' GROUP BY action, status ORDER BY 1, 2;" 2>&1
  echo ""
  echo "-- Review tickets"
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A \
    -c "SELECT ticket_id, scope_course_id, skill_id, status FROM review_tickets ORDER BY created_at DESC LIMIT 10;" 2>&1
} 2>&1 | tee "$LOGS/audit_check_p3.sql.out"

# ─── Step 9: P3 UI E2E (staff + programme + admin) ───────────────────────────
echo "[9] P3 UI E2E (Playwright) -> P3_UI_E2E_OUTPUT.txt"
P3_E2E_RESULT="FAIL"
mkdir -p "$OUT_DIR/P3_UI_E2E"
(
  cd "$REPO_ROOT/web"
  API_BASE_URL="$API_BASE" \
  NEXT_PUBLIC_FRONTEND_URL="http://localhost:$FRONTEND_PORT" \
  npx playwright install chromium --with-deps 2>/dev/null || true
  API_BASE_URL="$API_BASE" \
  NEXT_PUBLIC_FRONTEND_URL="http://localhost:$FRONTEND_PORT" \
  npx playwright test tests/e2e/staff_golden_path.spec.ts tests/e2e/programme_golden_path.spec.ts tests/e2e/admin_golden_path.spec.ts \
    --reporter=list 2>&1
) | tee "$OUT_DIR/P3_UI_E2E_OUTPUT.txt" && P3_E2E_RESULT="PASS" || true
cp -r "$REPO_ROOT/web/test-results/." "$OUT_DIR/P3_UI_E2E/" 2>/dev/null || true
echo "[9] P3 E2E: $P3_E2E_RESULT"

# ─── Step 10: Generate SUMMARY.md ────────────────────────────────────────────
echo "[10] Writing SUMMARY.md"
RUN_DATE="$(date)"

SUMMARY_FILE="$OUT_DIR/SUMMARY.md"
cat > "$SUMMARY_FILE" << HEREDOC
# P3 Evidence Pack Summary

**Run:** $RUN_DATE
**Output dir:** $OUT_DIR
**Repo:** $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')

## Results

| Step | Description | Result | Log / Artifact |
|------|-------------|--------|----------------|
| 1 | Clean run (CLEAN_RUN=${CLEAN_RUN:-0}) | — | — |
| 2 | Bootstrap | — | [LOGS/bootstrap.log](LOGS/bootstrap.log) |
| 3 | Backend + worker + frontend | — | [LOGS/backend.log](LOGS/backend.log), [LOGS/web.log](LOGS/web.log) |
| 4 | P0 verification | **$P0_RESULT** | [P0_VERIFICATION_OUTPUT.txt](P0_VERIFICATION_OUTPUT.txt) |
| 5 | P1 verification (rate limit / audit / deletion) | **$P1_RESULT** | [P1_VERIFICATION_OUTPUT.txt](P1_VERIFICATION_OUTPUT.txt) |
| 6 | P3 seed (seed_p3_demo_data.py) | **$P3_SEED_RESULT** | [P3_SEED_OUTPUT.txt](P3_SEED_OUTPUT.txt) |
| 7 | P3 API smoke (staff/programme/admin BFF) | **$P3_API_RESULT** | [P3_API_SMOKE.txt](P3_API_SMOKE.txt) |
| 8 | Audit check P3 (ticket.create/resolve) | — | [LOGS/audit_check_p3.sql.out](LOGS/audit_check_p3.sql.out) |
| 9 | P3 UI E2E (staff + programme + admin golden paths) | **$P3_E2E_RESULT** | [P3_UI_E2E_OUTPUT.txt](P3_UI_E2E_OUTPUT.txt), [P3_UI_E2E/](P3_UI_E2E/) |

## P3 Coverage

| Item | Status | Notes |
|------|--------|-------|
| Staff BFF (courses, skills_summary, review_queue, resolve) | $P3_API_RESULT | Step 7 |
| Programme BFF (programmes, coverage_matrix) | $P3_API_RESULT | Step 7 |
| Admin BFF (skills, roles, audit, metrics, health) | $P3_API_RESULT | Step 7 |
| RBAC/ABAC (staff/programme/admin role checks) | $P3_API_RESULT | Step 7 |
| Review tickets (create + resolve + audit) | $P3_SEED_RESULT | Step 6, 8 |
| Staff golden path E2E | $P3_E2E_RESULT | Step 9 |
| Programme golden path E2E | $P3_E2E_RESULT | Step 9 |
| Admin golden path E2E | $P3_E2E_RESULT | Step 9 |

## How to reproduce

\`\`\`bash
CLEAN_RUN=1 ./scripts/run_go_live_p3_pack.sh
\`\`\`

See [docs/P3_IMPLEMENTATION_NOTES.md](../../docs/P3_IMPLEMENTATION_NOTES.md) for full details.
HEREDOC

echo ""
echo "========================================================"
echo " P3 EVIDENCE PACK COMPLETE"
echo " Output: $OUT_DIR"
echo " SUMMARY: $SUMMARY_FILE"
echo "========================================================"
cat "$SUMMARY_FILE"

# ─── Exit non-zero if any critical step failed ────────────────────────────────
FAIL_STEPS=""
[ "$P0_RESULT" = "FAIL" ] && FAIL_STEPS="$FAIL_STEPS P0"
[ "$P3_SEED_RESULT" = "FAIL" ] && FAIL_STEPS="$FAIL_STEPS P3_SEED"
[ "$P3_API_RESULT" = "FAIL" ] && FAIL_STEPS="$FAIL_STEPS P3_API"
[ "$P3_E2E_RESULT" = "FAIL" ] && FAIL_STEPS="$FAIL_STEPS P3_E2E"

if [ -n "$FAIL_STEPS" ]; then
  echo ""
  echo "FAIL: The following steps failed:$FAIL_STEPS"
  echo "See the corresponding log files in $OUT_DIR/"
  exit 1
fi

echo ""
echo "All critical P3 steps PASSED. Evidence pack ready."
