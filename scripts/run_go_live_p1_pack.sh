#!/usr/bin/env bash
# Produce a complete P1 evidence pack: bootstrap, backend+worker, P0 verify, docker logs, audit SQL, rate-limit test, SUMMARY.
# Usage: ./scripts/run_go_live_p1_pack.sh
#   CLEAN_RUN=1  to run 'docker compose down -v' (ignore errors) before starting.
# Output: artifacts/go_live_baseline_p1/YYYYMMDD_HHMMSS/{LOGS/, P0_VERIFICATION_OUTPUT.txt, SUMMARY.md}
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

BACKEND_PORT="${BACKEND_PORT:-8001}"
DB_PORT="${DB_PORT:-55432}"
OUT_DIR="artifacts/go_live_baseline_p1/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT_DIR/LOGS"
LOGS="$OUT_DIR/LOGS"

BACKEND_PID=""
WORKER_PID=""

cleanup() {
  if [ -n "$BACKEND_PID" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "$WORKER_PID" ]; then
    kill "$WORKER_PID" 2>/dev/null || true
    wait "$WORKER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "== P1 evidence pack -> $OUT_DIR =="

# 1) Optional clean run
if [ "${CLEAN_RUN:-0}" = "1" ]; then
  echo "[1] CLEAN_RUN=1: docker compose down -v, stop backend/worker"
  docker compose down -v || true
  pkill -f "uvicorn backend.app.main" 2>/dev/null || true
  pkill -f "python.*worker\.py" 2>/dev/null || true
  sleep 2
fi

# 2) Bootstrap
echo "[2] Bootstrap"
./scripts/bootstrap_dev.sh 2>&1 | tee "$LOGS/bootstrap.log"
# Activate venv for remaining steps
VENV_DIR="${VENV_DIR:-$REPO_ROOT/venv}"
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://skillsight:skillsight@127.0.0.1:$DB_PORT/skillsight}"

# 3) Start backend and worker if not already running
API_BASE="http://127.0.0.1:$BACKEND_PORT"
backend_up() {
  curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "$API_BASE/health" 2>/dev/null | grep -q 200
}
worker_running() {
  pgrep -f "python.*worker\.py" >/dev/null 2>&1
}

if ! backend_up; then
  echo "[3] Starting backend on port $BACKEND_PORT (with rate limit env for step 7)"
  (cd "$REPO_ROOT/backend" && RATE_LIMIT_ENABLED=1 RATE_LIMIT_PER_MINUTE_AUTH=2 QDRANT_HOST=127.0.0.1 PYTHONPATH="$REPO_ROOT" uvicorn backend.app.main:app --host 0.0.0.0 --port "$BACKEND_PORT") 2>&1 | tee "$LOGS/backend.log" &
  BACKEND_PID=$!
  for i in {1..45}; do
    if backend_up; then break; fi
    [ "$i" -eq 45 ] && { echo "Backend did not become ready"; exit 1; }
    sleep 1
  done
  echo "Backend ready."
else
  echo "[3] Backend already running on port $BACKEND_PORT"
fi

if ! worker_running; then
  echo "[3] Starting worker"
  (cd "$REPO_ROOT" && python backend/worker.py) 2>&1 | tee "$LOGS/worker.log" &
  WORKER_PID=$!
  sleep 2
  echo "Worker started."
else
  echo "[3] Worker already running"
fi

# 4) P0 verification (script exits non-zero if this fails)
echo "[4] P0 verification -> P0_VERIFICATION_OUTPUT.txt"
./scripts/verify_p0.sh "$API_BASE" "$DB_PORT" 2>&1 | tee "$OUT_DIR/P0_VERIFICATION_OUTPUT.txt"
[ "${PIPESTATUS[0]}" -eq 0 ] || exit "${PIPESTATUS[0]}"

# 5) Docker evidence
echo "[5] Docker evidence"
docker compose ps > "$LOGS/docker_ps.log" 2>&1
docker compose logs --no-color > "$LOGS/docker_compose.log" 2>&1

# 6) Audit check (SQL from VERIFICATION.md: count by action/status + required actions)
echo "[6] Audit check -> LOGS/audit_check.sql.out"
{
  echo "-- Count by action, status (last hour)"
  echo "SELECT action, status, COUNT(*) AS n FROM audit_logs WHERE created_at > now() - interval '1 hour' GROUP BY action, status ORDER BY action, status;"
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A -c "SELECT action, status, COUNT(*) AS n FROM audit_logs WHERE created_at > now() - interval '1 hour' GROUP BY action, status ORDER BY action, status;"
  echo ""
  echo "-- Required actions (e2e)"
  echo "SELECT action FROM audit_logs WHERE created_at > now() - interval '1 hour' AND action IN ('auth.dev_login','documents.import','search.evidence_vector','ai.demonstration','assess.role_readiness','actions.recommend');"
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A -c "SELECT action FROM audit_logs WHERE created_at > now() - interval '1 hour' AND action IN ('auth.dev_login','documents.import','search.evidence_vector','ai.demonstration','assess.role_readiness','actions.recommend');"
  echo ""
  echo "-- Minimal: action, status, count (all time)"
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -c "SELECT action, status, COUNT(*) FROM audit_logs GROUP BY 1, 2 ORDER BY 1, 2;"
} 2>&1 | tee "$LOGS/audit_check.sql.out"

# 7) Rate limit check
echo "[7] Rate limit check -> LOGS/rate_limit_test.log"
RATE_LIMIT_ENABLED=1 RATE_LIMIT_PER_MINUTE_AUTH=2 ./scripts/test_rate_limit.sh "$API_BASE" 2>&1 | tee "$LOGS/rate_limit_test.log"

# 8) SUMMARY.md
echo "[8] Writing SUMMARY.md"
P0_PASS="FAIL"
grep -q "PASS" "$OUT_DIR/P0_VERIFICATION_OUTPUT.txt" && P0_PASS="PASS"
RATE_PASS="FAIL"
grep -q "HTTP 429" "$LOGS/rate_limit_test.log" && RATE_PASS="PASS"

cat > "$OUT_DIR/SUMMARY.md" << EOF
# P1 Evidence Pack Summary

**Run:** $(date -Iseconds 2>/dev/null || date)
**Output dir:** $OUT_DIR

| Step | Result | Log / artifact |
|------|--------|----------------|
| 1. Clean run (if CLEAN_RUN=1) | - | - |
| 2. Bootstrap | (see log) | [LOGS/bootstrap.log](LOGS/bootstrap.log) |
| 3. Backend + worker | (see logs) | [LOGS/backend.log](LOGS/backend.log), [LOGS/worker.log](LOGS/worker.log) |
| 4. P0 verification | **$P0_PASS** | [P0_VERIFICATION_OUTPUT.txt](P0_VERIFICATION_OUTPUT.txt) |
| 5. Docker evidence | - | [LOGS/docker_ps.log](LOGS/docker_ps.log), [LOGS/docker_compose.log](LOGS/docker_compose.log) |
| 6. Audit check | - | [LOGS/audit_check.sql.out](LOGS/audit_check.sql.out) |
| 7. Rate limit test | **$RATE_PASS** | [LOGS/rate_limit_test.log](LOGS/rate_limit_test.log) |

**Overall:** P0 verification must PASS for go-live. Script exits non-zero if verify_p0 fails.
EOF

if [ "$RATE_PASS" = "FAIL" ]; then
  echo ""
  echo "FAIL: Rate limit test did not observe HTTP 429. See $LOGS/rate_limit_test.log"
  exit 1
fi

echo ""
echo "== Done. Evidence pack: $OUT_DIR =="
echo "SUMMARY: $OUT_DIR/SUMMARY.md"
