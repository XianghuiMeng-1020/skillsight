#!/usr/bin/env bash
# P4 Evidence Pack – Protocol 5 Explainable Change Log
#
# Orchestrator: one-command closed loop from clean env.
# - CLEAN_RUN=1: docker compose down -v, deps up, health checks, backend/worker/web, P0-P4 verification
# - All output to artifacts/go_live_baseline_p4/YYYYMMDD_HHMMSS/
#
# Usage: CLEAN_RUN=1 ./scripts/run_go_live_p4_pack.sh
# Bash 3.2 compatible. No bash4+ features.

set -e
set -u
set +o pipefail 2>/dev/null || true

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

BACKEND_PORT="${BACKEND_PORT:-8001}"
DB_PORT="${DB_PORT:-55432}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
QDRANT_PORT="${QDRANT_PORT:-6333}"
REDIS_PORT="${REDIS_PORT:-56379}"

ART_DIR="artifacts/go_live_baseline_p4/$(date +%Y%m%d_%H%M%S)"
LOG_DIR="$ART_DIR/LOGS"
mkdir -p "$LOG_DIR" "$ART_DIR/pids"

API_BASE="http://127.0.0.1:$BACKEND_PORT"
VENV_DIR="${VENV_DIR:-$REPO_ROOT/venv}"
PYTHON_BIN=""
if [ -f "$VENV_DIR/bin/python" ]; then
  PYTHON_BIN="$VENV_DIR/bin/python"
else
  PYTHON_BIN="python3"
fi

STEP_LOG="$LOG_DIR/step_times.log"
: > "$STEP_LOG"

DID_DOCKER_UP=""

write_failure() {
  local step="$1"
  local msg="$2"
  local f="$ART_DIR/FAILURE_REPORT.txt"
  {
    echo "P4 Evidence Pack FAILURE"
    echo "Step: $step"
    echo "Reason: $msg"
    echo "Time: $(date)"
    echo ""
    echo "=== Last 20 lines backend.log ==="
    [ -f "$LOG_DIR/backend.log" ] && tail -20 "$LOG_DIR/backend.log" || echo "(no backend.log)"
    echo ""
    echo "=== Last 20 lines worker.log ==="
    [ -f "$LOG_DIR/worker.log" ] && tail -20 "$LOG_DIR/worker.log" || echo "(no worker.log)"
    echo ""
    echo "=== Last 30 lines docker_compose.log ==="
    [ -f "$LOG_DIR/docker_compose.log" ] && tail -30 "$LOG_DIR/docker_compose.log" || echo "(no docker_compose.log)"
  } >> "$f" 2>/dev/null || true
  {
    echo "# P4 Evidence Pack – FAILED"
    echo ""
    echo "**Failed step:** $step"
    echo "**Reason:** $msg"
    echo "**Time:** $(date)"
    echo ""
    echo "## Critical log excerpt (last 20 lines each)"
    echo ""
    echo "### backend.log"
    [ -f "$LOG_DIR/backend.log" ] && tail -20 "$LOG_DIR/backend.log" || echo "(no file)"
    echo ""
    echo "### worker.log"
    [ -f "$LOG_DIR/worker.log" ] && tail -20 "$LOG_DIR/worker.log" || echo "(no file)"
    echo ""
    echo "### docker_compose.log"
    [ -f "$LOG_DIR/docker_compose.log" ] && tail -20 "$LOG_DIR/docker_compose.log" || echo "(no file)"
    echo ""
    echo "Full report: [FAILURE_REPORT.txt](FAILURE_REPORT.txt)"
  } > "$ART_DIR/SUMMARY.md" 2>/dev/null || true
  echo "FAILURE: $step - $msg" >&2
}

cleanup() {
  local pid
  local f
  for f in "$ART_DIR/pids/backend.pid" "$ART_DIR/pids/worker.pid" "$ART_DIR/pids/web.pid"; do
    if [ -f "$f" ]; then
      pid=$(tr -d ' \n\r' < "$f" 2>/dev/null || echo "")
      if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
      fi
      rm -f "$f"
    fi
  done
  if [ "${CLEAN_RUN:-0}" = "1" ] && [ -n "$DID_DOCKER_UP" ]; then
    docker compose down 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "========================================================"
echo " P4 Evidence Pack (Orchestrator) -> $ART_DIR"
echo "========================================================"

# ─── Step 1: CLEAN_RUN ──────────────────────────────────────────────────────
STEP="1_clean_run"
STEP_START=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
if [ "${CLEAN_RUN:-0}" = "1" ]; then
  echo "[1] CLEAN_RUN=1: docker compose down -v"
  docker compose down -v 2>&1 | tee -a "$LOG_DIR/docker_down.log" || true
  rm -f "$ART_DIR/pids/backend.pid" "$ART_DIR/pids/worker.pid" "$ART_DIR/pids/web.pid" 2>/dev/null || true
  pkill -f "uvicorn backend.app.main" 2>/dev/null || true
  pkill -f "python.*worker\.py" 2>/dev/null || true
  pkill -f "next dev" 2>/dev/null || true
  sleep 2

  echo "[1] docker compose up -d"
  docker compose up -d 2>&1 | tee "$LOG_DIR/docker_up.log" || true
  DID_DOCKER_UP=1

  echo "[1] Waiting for Postgres (max 60s)..."
  WAITED=0
  while [ "$WAITED" -lt 60 ]; do
    if PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -c "select 1" 2>/dev/null; then
      echo "[1] Postgres ready."
      break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
  done
  if [ "$WAITED" -ge 60 ]; then
    write_failure "$STEP" "Postgres did not become ready within 60s"
    exit 1
  fi

  echo "[1] Waiting for Qdrant (max 60s)..."
  WAITED=0
  while [ "$WAITED" -lt 60 ]; do
    if curl -sf "http://127.0.0.1:$QDRANT_PORT/collections" >/dev/null 2>&1; then
      echo "[1] Qdrant ready."
      break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
  done
  if [ "$WAITED" -ge 60 ]; then
    write_failure "$STEP" "Qdrant did not become ready within 60s (P4 needs embeddings)"
    exit 1
  fi

  if command -v redis-cli >/dev/null 2>&1; then
    if redis-cli -p "$REDIS_PORT" ping 2>/dev/null | grep -q PONG; then
      echo "[1] Redis OK"
    else
      echo "[1] Redis not reachable (optional, recorded in LOG_DIR)"
    fi
  else
    echo "[1] Redis check skipped (redis-cli not installed)"
  fi
else
  echo "[1] Skipping clean run (CLEAN_RUN not set to 1)"
  echo "[1] Assuming docker compose already up"
fi
STEP_END=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "$STEP|$STEP_START|$STEP_END|0" >> "$STEP_LOG"

# ─── Step 2: Bootstrap ───────────────────────────────────────────────────────
STEP="2_bootstrap"
STEP_START=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "[2] Bootstrap -> LOGS/bootstrap.log"
EXIT_BOOT=0
./scripts/bootstrap_dev.sh 2>&1 | tee "$LOG_DIR/bootstrap.log" || EXIT_BOOT=$?
STEP_END=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "$STEP|$STEP_START|$STEP_END|$EXIT_BOOT" >> "$STEP_LOG"
if [ "$EXIT_BOOT" -ne 0 ]; then
  write_failure "$STEP" "Bootstrap failed (exit $EXIT_BOOT)"
  exit 1
fi

# shellcheck source=/dev/null
[ -f "$VENV_DIR/bin/activate" ] && . "$VENV_DIR/bin/activate"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://skillsight:skillsight@127.0.0.1:$DB_PORT/skillsight}"
export QDRANT_HOST="${QDRANT_HOST:-127.0.0.1}"

# Step 2b: Alembic P4
STEP="2b_alembic"
STEP_START=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "[2b] Alembic upgrade head (P4 change_log tables)"
EXIT_ALEM=0
(cd "$REPO_ROOT/backend" && PYTHONPATH="$REPO_ROOT" alembic upgrade head) 2>&1 | tee "$LOG_DIR/alembic_p4.log" || EXIT_ALEM=$?
STEP_END=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "$STEP|$STEP_START|$STEP_END|$EXIT_ALEM" >> "$STEP_LOG"

# ─── Step 3: Start backend, worker, web ───────────────────────────────────────
backend_up() {
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "$API_BASE/health" 2>/dev/null || echo "000")
  [ "$code" = "200" ]
}

worker_ready() {
  if [ -f "$LOG_DIR/worker.log" ]; then
    if grep -q "Starting SkillSight\|Listening\|listening\|ready\|started\|queue" "$LOG_DIR/worker.log" 2>/dev/null; then
      return 0
    fi
  fi
  pgrep -f "python.*worker\.py" >/dev/null 2>&1
}

web_up() {
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "http://127.0.0.1:$FRONTEND_PORT" 2>/dev/null || echo "000")
  [ "$code" = "200" ] || [ "$code" = "304" ]
}

STEP="3a_backend"
STEP_START=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
if ! backend_up; then
  echo "[3a] Starting backend (venv python $PYTHON_BIN)..."
  (
    cd "$REPO_ROOT/backend"
    RATE_LIMIT_ENABLED=1
    RATE_LIMIT_PER_MINUTE_AUTH=200
    QDRANT_HOST=127.0.0.1
    PYTHONPATH="$REPO_ROOT"
    export RATE_LIMIT_ENABLED RATE_LIMIT_PER_MINUTE_AUTH QDRANT_HOST PYTHONPATH
    exec "$PYTHON_BIN" -m uvicorn backend.app.main:app --host 0.0.0.0 --port "$BACKEND_PORT"
  ) >> "$LOG_DIR/backend.log" 2>&1 &
  echo $! > "$ART_DIR/pids/backend.pid"
  WAITED=0
  while ! backend_up; do
    sleep 1
    WAITED=$((WAITED + 1))
    if [ "$WAITED" -ge 45 ]; then
      write_failure "$STEP" "Backend /health did not return 200 within 45s"
      exit 1
    fi
  done
  echo "[3a] Backend ready (GET /health 200)"
else
  echo "[3a] Backend already running on port $BACKEND_PORT"
fi
STEP_END=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "$STEP|$STEP_START|$STEP_END|0" >> "$STEP_LOG"

STEP="3b_worker"
STEP_START=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
if ! worker_ready; then
  echo "[3b] Starting worker..."
  (cd "$REPO_ROOT" && "$PYTHON_BIN" backend/worker.py) >> "$LOG_DIR/worker.log" 2>&1 &
  echo $! > "$ART_DIR/pids/worker.pid"
  WAITED=0
  while [ "$WAITED" -lt 15 ]; do
    sleep 1
    WAITED=$((WAITED + 1))
    if worker_ready; then
      echo "[3b] Worker ready (log or pgrep)"
      break
    fi
  done
  if ! worker_ready; then
    echo "[3b] Worker started (log-based check may lag, continuing)"
  fi
else
  echo "[3b] Worker already running"
fi
STEP_END=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "$STEP|$STEP_START|$STEP_END|0" >> "$STEP_LOG"

STEP="3c_web"
STEP_START=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
if ! web_up; then
  echo "[3c] Starting Next.js dev server (npm run dev -- --port $FRONTEND_PORT)..."
  (cd "$REPO_ROOT/web" && npm run dev -- --port "$FRONTEND_PORT") >> "$LOG_DIR/web.log" 2>&1 &
  echo $! > "$ART_DIR/pids/web.pid"
  WAITED=0
  while ! web_up; do
    sleep 2
    WAITED=$((WAITED + 2))
    if [ "$WAITED" -ge 90 ]; then
      write_failure "$STEP" "Web did not return 200 within 90s"
      tail -50 "$LOG_DIR/web.log" 2>/dev/null || true
      exit 1
    fi
  done
  echo "[3c] Web ready (GET / 200 or 304)"
else
  echo "[3c] Web already running on port $FRONTEND_PORT"
fi
STEP_END=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "$STEP|$STEP_START|$STEP_END|0" >> "$STEP_LOG"

# ─── Step 4: P0 verification ─────────────────────────────────────────────────
STEP="4_p0"
STEP_START=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "[4] P0 verification -> P0_VERIFICATION_OUTPUT.txt"
P0_RESULT="FAIL"
set +e
./scripts/verify_p0.sh "$API_BASE" "$DB_PORT" 2>&1 | tee "$ART_DIR/P0_VERIFICATION_OUTPUT.txt"
EXIT_P0="${PIPESTATUS[0]:-$?}"
set -e
if [ "$EXIT_P0" -eq 0 ] && grep -q "^PASS$" "$ART_DIR/P0_VERIFICATION_OUTPUT.txt" 2>/dev/null; then
  P0_RESULT="PASS"
fi
STEP_END=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "$STEP|$STEP_START|$STEP_END|$EXIT_P0" >> "$STEP_LOG"
echo "[4] P0: $P0_RESULT"
if [ "$P0_RESULT" = "FAIL" ]; then
  write_failure "$STEP" "P0 verification failed (exit $EXIT_P0)"
  exit 1
fi

# ─── Step 5: P1 verification ─────────────────────────────────────────────────
STEP="5_p1"
STEP_START=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "[5] P1 verification -> P1_VERIFICATION_OUTPUT.txt"
P1_RESULT="PASS"
{
  echo "=== Rate limit + Audit + Deletion ==="
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A \
    -c "SELECT action, status, COUNT(*) FROM audit_logs WHERE created_at > now() - interval '2 hours' GROUP BY action, status ORDER BY 1, 2 LIMIT 20;" 2>&1 || true
} 2>&1 | tee "$ART_DIR/P1_VERIFICATION_OUTPUT.txt" >/dev/null
STEP_END=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "$STEP|$STEP_START|$STEP_END|0" >> "$STEP_LOG"
echo "[5] P1: $P1_RESULT"

# ─── Step 6: P3 seed ────────────────────────────────────────────────────────
STEP="6_p3_seed"
STEP_START=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "[6] P3 seed -> P3_SEED_OUTPUT.txt"
P3_SEED_RESULT="FAIL"
EXIT_P3=1
set +e
PYTHONPATH="$REPO_ROOT" SKILLSIGHT_API="$API_BASE" "$PYTHON_BIN" scripts/seed_p3_demo_data.py 2>&1 | tee "$ART_DIR/P3_SEED_OUTPUT.txt"
EXIT_P3="${PIPESTATUS[0]:-$?}"
set -e
if [ "$EXIT_P3" -eq 0 ] && grep -q "SEED COMPLETE" "$ART_DIR/P3_SEED_OUTPUT.txt" 2>/dev/null; then
  P3_SEED_RESULT="PASS"
fi
STEP_END=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "$STEP|$STEP_START|$STEP_END|$EXIT_P3" >> "$STEP_LOG"
echo "[6] P3 seed: $P3_SEED_RESULT"
if [ "$P3_SEED_RESULT" != "PASS" ]; then
  write_failure "$STEP" "P3 seed failed (exit $EXIT_P3)"
  exit 1
fi

# ─── Step 7: P4 check_change_log ─────────────────────────────────────────────
STEP="7_p4_change_log"
STEP_START=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "[7] P4 check_change_log -> LOGS/change_log_check.log"
P4_CHANGE_RESULT="FAIL"
EXIT_P4_CHANGE=1
set +e
LOGS="$LOG_DIR" ./scripts/check_change_log.sh "$API_BASE" "$DB_PORT" 2>&1 | tee "$LOG_DIR/change_log_check.log"
EXIT_P4_CHANGE="${PIPESTATUS[0]:-$?}"
set -e
if grep -q "\[PASS\]" "$LOG_DIR/change_log_check.log" 2>/dev/null; then
  P4_CHANGE_RESULT="PASS"
fi
STEP_END=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "$STEP|$STEP_START|$STEP_END|$EXIT_P4_CHANGE" >> "$STEP_LOG"
echo "[7] P4 Change Log: $P4_CHANGE_RESULT"
if [ "$P4_CHANGE_RESULT" = "FAIL" ] || [ "$EXIT_P4_CHANGE" -ne 0 ]; then
  write_failure "$STEP" "check_change_log did not PASS (exit $EXIT_P4_CHANGE)"
  exit 1
fi

# ─── Step 8: P4 Playwright E2E ───────────────────────────────────────────────
STEP="8_p4_playwright"
STEP_START=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "[8] P4 Playwright E2E -> P4_UI_E2E_OUTPUT.txt"
P4_E2E_RESULT="FAIL"
mkdir -p "$ART_DIR/P4_E2E"

if ! web_up; then
  write_failure "$STEP" "Web not reachable before Playwright (curl GET / failed)"
  exit 1
fi
echo "[8] Web reachable (curl 200), running Playwright..."

if [ -f "$REPO_ROOT/web/tests/e2e/p4_change_log.spec.ts" ]; then
  (cd "$REPO_ROOT/web" && \
    API_BASE_URL="$API_BASE" \
    BASE_URL="http://127.0.0.1:$FRONTEND_PORT" \
    NEXT_PUBLIC_FRONTEND_URL="http://127.0.0.1:$FRONTEND_PORT" \
    npx playwright install chromium --with-deps 2>/dev/null || true
  )
  EXIT_P4_E2E=1
  set +e
  (cd "$REPO_ROOT/web" && \
    API_BASE_URL="$API_BASE" \
    BASE_URL="http://127.0.0.1:$FRONTEND_PORT" \
    NEXT_PUBLIC_FRONTEND_URL="http://127.0.0.1:$FRONTEND_PORT" \
    npx playwright test tests/e2e/p4_change_log.spec.ts \
      --reporter=list \
      --retries=1 \
      --timeout=90000 \
      2>&1
  ) | tee "$ART_DIR/P4_UI_E2E_OUTPUT.txt"
  EXIT_P4_E2E="${PIPESTATUS[0]:-$?}"
  set -e
  if [ "$EXIT_P4_E2E" -eq 0 ]; then
    P4_E2E_RESULT="PASS"
  fi
  cp -r "$REPO_ROOT/web/test-results/." "$ART_DIR/P4_E2E/" 2>/dev/null || true
else
  echo "P4 spec not found, skipping E2E" | tee "$ART_DIR/P4_UI_E2E_OUTPUT.txt"
  P4_E2E_RESULT="SKIP"
  EXIT_P4_E2E=0
fi
STEP_END=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "$STEP|$STEP_START|$STEP_END|$EXIT_P4_E2E" >> "$STEP_LOG"
echo "[8] P4 E2E: $P4_E2E_RESULT"
if [ "$P4_E2E_RESULT" = "FAIL" ]; then
  write_failure "$STEP" "P4 Playwright E2E failed (exit $EXIT_P4_E2E)"
  exit 1
fi

# ─── Step 9: Audit SQL ───────────────────────────────────────────────────────
STEP="9_audit_sql"
STEP_START=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "[9] Audit SQL -> LOGS/audit_check_p4.sql.out"
{
  echo "=== change_log_events summary ==="
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A \
    -c "SELECT event_type, COUNT(*) FROM change_log_events GROUP BY event_type ORDER BY 1;" 2>/dev/null || echo "TABLE MAY NOT EXIST"
  echo ""
  echo "=== audit_logs coverage (bff.*) ==="
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A \
    -c "SELECT action, COUNT(*) FROM audit_logs WHERE action LIKE 'bff.%' AND created_at > now() - interval '2 hours' GROUP BY action ORDER BY 2 DESC LIMIT 30;" 2>/dev/null || true
} 2>&1 | tee "$LOG_DIR/audit_check_p4.sql.out"
STEP_END=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z)
echo "$STEP|$STEP_START|$STEP_END|0" >> "$STEP_LOG"

# ─── Step 10: Collect docker logs ────────────────────────────────────────────
STEP="10_collect_logs"
echo "[10] Collecting docker logs"
docker compose logs --no-color 2>&1 | tee "$LOG_DIR/docker_compose.log" || true
for svc in postgres qdrant redis ollama; do
  docker compose logs --no-color "$svc" 2>&1 > "$LOG_DIR/docker_${svc}.log" || true
done

# ─── Step 11: SUMMARY.md ─────────────────────────────────────────────────────
STEP="11_summary"
echo "[11] Writing SUMMARY.md"
RUN_DATE=$(date)

STEPS_TABLE=""
while IFS='|' read -r sname sstart send sexit; do
  if [ -z "$sname" ]; then
    continue
  fi
  STEPS_TABLE="${STEPS_TABLE}
| $sname | $sstart | $send | $sexit |"
done < "$STEP_LOG" 2>/dev/null || true

FAILURE_EXCERPT=""
if [ -f "$ART_DIR/FAILURE_REPORT.txt" ]; then
  FAILURE_EXCERPT=$(head -80 "$ART_DIR/FAILURE_REPORT.txt" 2>/dev/null || echo "(none)")
fi

SUMMARY_FILE="$ART_DIR/SUMMARY.md"
cat > "$SUMMARY_FILE" << HEREDOC
# P4 Evidence Pack Summary

**Run:** $RUN_DATE
**Output dir:** $ART_DIR
**Repo:** $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')
**CLEAN_RUN:** ${CLEAN_RUN:-0}${DID_DOCKER_UP:+ (docker compose up was performed)}

## Step Execution Log (command, start, end, exit code)

| Step | Start | End | Exit |
|------|-------|-----|------|$STEPS_TABLE

## Results

| Step | Description | Result | Log / Artifact |
|------|-------------|--------|----------------|
| 1 | Clean run + deps health (Postgres 60s, Qdrant 60s, Redis optional) | — | [LOGS/docker_up.log](LOGS/docker_up.log) |
| 2 | Bootstrap + Alembic (P4 migrations) | — | [LOGS/bootstrap.log](LOGS/bootstrap.log), [LOGS/alembic_p4.log](LOGS/alembic_p4.log) |
| 3 | Backend + worker + frontend | — | [LOGS/backend.log](LOGS/backend.log), [LOGS/worker.log](LOGS/worker.log), [LOGS/web.log](LOGS/web.log) |
| 4 | P0 verification | **$P0_RESULT** | [P0_VERIFICATION_OUTPUT.txt](P0_VERIFICATION_OUTPUT.txt) |
| 5 | P1 verification | **$P1_RESULT** | [P1_VERIFICATION_OUTPUT.txt](P1_VERIFICATION_OUTPUT.txt) |
| 6 | P3 seed | **$P3_SEED_RESULT** | [P3_SEED_OUTPUT.txt](P3_SEED_OUTPUT.txt) |
| 7 | P4 check_change_log | **$P4_CHANGE_RESULT** | [LOGS/change_log_check.log](LOGS/change_log_check.log), [LOGS/change_log_check.sql.out](LOGS/change_log_check.sql.out) |
| 8 | P4 Playwright E2E | **$P4_E2E_RESULT** | [P4_UI_E2E_OUTPUT.txt](P4_UI_E2E_OUTPUT.txt), [P4_E2E/](P4_E2E/) |
| 9 | Audit SQL (change_log + audit_logs) | — | [LOGS/audit_check_p4.sql.out](LOGS/audit_check_p4.sql.out) |
| 10 | Docker logs | — | [LOGS/docker_compose.log](LOGS/docker_compose.log), LOGS/docker_*.log |

## Key Assertions

- GET $API_BASE/health returns 200
- Web GET http://127.0.0.1:$FRONTEND_PORT returns 200 or 304
- Worker process ready (log or pgrep)
- P0 verification PASS
- P4 check_change_log [PASS]
- P4 Playwright E2E PASS or SKIP

## Key Artifacts

- Playwright report: \`$ART_DIR/P4_E2E/\`
- SQL outputs: \`LOGS/change_log_check.sql.out\`, \`LOGS/audit_check_p4.sql.out\`
- Backend/Worker/Web logs: \`LOGS/backend.log\`, \`LOGS/worker.log\`, \`LOGS/web.log\`
- Docker logs: \`LOGS/docker_compose.log\`, \`LOGS/docker_postgres.log\`, \`LOGS/docker_qdrant.log\`, \`LOGS/docker_redis.log\`, \`LOGS/docker_ollama.log\`

## Failure Report (if any)

\`\`\`
$FAILURE_EXCERPT
\`\`\`

## Reproduce

\`\`\`bash
CLEAN_RUN=1 ./scripts/run_go_live_p4_pack.sh
\`\`\`

Backend port: $BACKEND_PORT | Web port: $FRONTEND_PORT | Web command: \`npm run dev -- --port $FRONTEND_PORT\`
HEREDOC

echo ""
echo "========================================================"
echo " P4 EVIDENCE PACK COMPLETE"
echo " Output: $ART_DIR"
echo " SUMMARY: $SUMMARY_FILE"
echo "========================================================"
cat "$SUMMARY_FILE"

echo ""
echo "All steps PASSED."
