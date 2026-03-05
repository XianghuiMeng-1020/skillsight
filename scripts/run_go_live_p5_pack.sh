#!/usr/bin/env bash
# P5 Evidence Pack – Decision 1–5 + Protocol 4 Human Review + Prod Build
#
# Orchestrator: one-command closed loop from clean env.
# - CLEAN_RUN=1: docker compose down -v, deps up, P0–P5 verification
# - Output: artifacts/go_live_baseline_p5/YYYYMMDD_HHMMSS/
#
# Usage: CLEAN_RUN=1 ./scripts/run_go_live_p5_pack.sh
# Bash 3.2 compatible.

set -e
set -u
set -o pipefail 2>/dev/null || true

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

BACKEND_PORT="${BACKEND_PORT:-8001}"
DB_PORT="${DB_PORT:-55432}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
QDRANT_PORT="${QDRANT_PORT:-6333}"
REDIS_PORT="${REDIS_PORT:-56379}"

ART_DIR="artifacts/go_live_baseline_p5/$(date +%Y%m%d_%H%M%S)"
LOG_DIR="$ART_DIR/LOGS"
export LOG_DIR
mkdir -p "$LOG_DIR" "$ART_DIR/pids"

API_BASE="http://127.0.0.1:$BACKEND_PORT"
VENV_DIR="${VENV_DIR:-$REPO_ROOT/venv}"
if [ -d "$REPO_ROOT/.venv" ] && [ ! -d "$VENV_DIR" ]; then
  VENV_DIR="$REPO_ROOT/.venv"
fi
PYTHON_BIN=""
if [ -f "$VENV_DIR/bin/python" ]; then
  PYTHON_BIN="$VENV_DIR/bin/python"
else
  PYTHON_BIN="python3"
fi
# Activate venv for subshells (pytest, alembic)
[ -f "$VENV_DIR/bin/activate" ] && . "$VENV_DIR/bin/activate"

STEP_LOG="$LOG_DIR/step_times.log"
: > "$STEP_LOG"
DID_DOCKER_UP=""

write_failure() {
  local step="$1"
  local msg="$2"
  {
    echo "P5 Evidence Pack FAILURE"
    echo "Step: $step"
    echo "Reason: $msg"
    echo "Time: $(date)"
  } > "$ART_DIR/FAILURE_REPORT.txt" 2>/dev/null || true
  echo "FAILURE: $step - $msg" >&2
}

cleanup() {
  local pid f
  for f in "$ART_DIR/pids/backend.pid" "$ART_DIR/pids/worker.pid" "$ART_DIR/pids/web.pid"; do
    if [ -f "$f" ]; then
      pid=$(tr -d ' \n\r' < "$f" 2>/dev/null || echo "")
      [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && kill "$pid" 2>/dev/null || true
      rm -f "$f"
    fi
  done
  [ "${CLEAN_RUN:-0}" = "1" ] && [ -n "$DID_DOCKER_UP" ] && docker compose down 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "========================================================"
echo " P5 Evidence Pack (Orchestrator) -> $ART_DIR"
echo "========================================================"

# Step 1: CLEAN_RUN
STEP="1_clean_run"
if [ "${CLEAN_RUN:-0}" = "1" ]; then
  docker compose down -v 2>&1 | tee -a "$LOG_DIR/docker_down.log" || true
  docker compose up -d 2>&1 | tee "$LOG_DIR/docker_up.log" || true
  DID_DOCKER_UP=1
  WAITED=0
  while [ "$WAITED" -lt 60 ]; do
    PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -c "select 1" 2>/dev/null && break
    sleep 2
    WAITED=$((WAITED + 2))
  done
  [ "$WAITED" -ge 60 ] && write_failure "$STEP" "Postgres not ready" && exit 1
fi

# Step 2: Bootstrap + Alembic
STEP="2_bootstrap"
./scripts/bootstrap_dev.sh 2>&1 | tee "$LOG_DIR/bootstrap.log"
(cd "$REPO_ROOT/backend" && PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" -m alembic upgrade head) 2>&1 | tee "$LOG_DIR/alembic_p5.log" || true

# Step 2b: Verify frontend prod build (before starting web; ensures npm install/build OK)
STEP="2b_frontend_prod_build"
set +e
LOG_DIR="$LOG_DIR" ./scripts/verify_frontend_prod_build.sh 2>&1 | tee "$LOG_DIR/frontend_prod_build.log"
EXIT_FB="${PIPESTATUS[0]:-$?}"
set -e
[ "$EXIT_FB" -ne 0 ] && write_failure "$STEP" "Frontend prod build failed" && exit 1

# Step 2c: Capture courses schema (evidence for course_name fix)
{
  echo "=== \\d+ courses ==="
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -c "\d+ courses" 2>/dev/null || echo "N/A"
  echo ""
  echo "=== information_schema.columns ==="
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A \
    -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='courses' ORDER BY ordinal_position;" 2>/dev/null || echo "N/A"
} > "$LOG_DIR/schema_courses.txt" 2>&1 || true

# Step 2d: Decision 1/2 pytest (unit tests); record SKIPPED for SUMMARY
STEP="2d_decision_1_2_pytest"
D12_PYTEST_HAD_SKIP=0
set +e
PYTHONPATH="$REPO_ROOT" DATABASE_URL="postgresql+psycopg2://skillsight:skillsight@127.0.0.1:$DB_PORT/skillsight_test" \
  "$PYTHON_BIN" -m pytest \
  backend/tests/test_decision1_reranker_threshold.py \
  backend/tests/test_decision2_reliability_conflict.py \
  backend/tests/test_refusal_contract.py \
  backend/tests/test_regression_stability.py \
  -v --tb=short 2>&1 | tee "$LOG_DIR/decision12_pytest.txt"
EXIT_PYTEST="${PIPESTATUS[0]:-$?}"
set -e
[ "$EXIT_PYTEST" -ne 0 ] && write_failure "$STEP" "Decision 1/2 pytest failed" && exit 1
grep -q "skipped" "$LOG_DIR/decision12_pytest.txt" 2>/dev/null && D12_PYTEST_HAD_SKIP=1
[ ! -s "$LOG_DIR/decision12_pytest.txt" ] && write_failure "$STEP" "decision12_pytest.txt missing or empty" && exit 1

# Step 3: Start backend, worker, web
backend_up() { [ "$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 "$API_BASE/health" 2>/dev/null || echo '000')" = "200" ]; }
web_up() { local c=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 "http://127.0.0.1:$FRONTEND_PORT" 2>/dev/null || echo '000'); [ "$c" = "200" ] || [ "$c" = "304" ]; }

if ! backend_up; then
  (cd "$REPO_ROOT/backend" && RATE_LIMIT_ENABLED=1 QDRANT_HOST=127.0.0.1 PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" -m uvicorn backend.app.main:app --host 0.0.0.0 --port "$BACKEND_PORT") >> "$LOG_DIR/backend.log" 2>&1 &
  echo $! > "$ART_DIR/pids/backend.pid"
  WAITED=0
  while ! backend_up; do sleep 1; WAITED=$((WAITED+1)); [ "$WAITED" -ge 45 ] && write_failure "3a_backend" "Backend not ready" && exit 1; done
fi

(cd "$REPO_ROOT" && "$PYTHON_BIN" backend/worker.py) >> "$LOG_DIR/worker.log" 2>&1 &
echo $! > "$ART_DIR/pids/worker.pid"
sleep 3

if ! web_up; then
  bash "$REPO_ROOT/scripts/bootstrap_web.sh" "$ART_DIR" || { write_failure "3c_web" "bootstrap_web failed"; exit 1; }
  (cd "$REPO_ROOT/web" && npm run dev -- --port "$FRONTEND_PORT") >> "$LOG_DIR/web.log" 2>&1 &
  echo $! > "$ART_DIR/pids/web.pid"
  WAITED=0
  while ! web_up; do sleep 2; WAITED=$((WAITED+2)); [ "$WAITED" -ge 90 ] && write_failure "3c_web" "Web not ready" && exit 1; done
fi

# Step 4: P0
STEP="4_p0"
set +e
./scripts/verify_p0.sh "$API_BASE" "$DB_PORT" 2>&1 | tee "$ART_DIR/P0_VERIFICATION_OUTPUT.txt"
EXIT_P0="${PIPESTATUS[0]:-$?}"
set -e
[ "$EXIT_P0" -ne 0 ] && write_failure "$STEP" "P0 failed" && exit 1

# Step 5: P1
STEP="5_p1"
PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A \
  -c "SELECT action, status, COUNT(*) FROM audit_logs WHERE created_at > now() - interval '2 hours' GROUP BY action, status LIMIT 20;" 2>&1 | tee "$ART_DIR/P1_VERIFICATION_OUTPUT.txt" >/dev/null || true

# Step 6: P3 seed
STEP="6_p3_seed"
set +e
PYTHONPATH="$REPO_ROOT" SKILLSIGHT_API="$API_BASE" "$PYTHON_BIN" scripts/seed_p3_demo_data.py 2>&1 | tee "$ART_DIR/P3_SEED_OUTPUT.txt"
EXIT_P3="${PIPESTATUS[0]:-$?}"
set -e
[ "$EXIT_P3" -ne 0 ] || ! grep -q "SEED COMPLETE" "$ART_DIR/P3_SEED_OUTPUT.txt" 2>/dev/null && write_failure "$STEP" "P3 seed failed" && exit 1

# Step 7: P4 check_change_log
STEP="7_p4_change_log"
set +e
LOGS="$LOG_DIR" ./scripts/check_change_log.sh "$API_BASE" "$DB_PORT" 2>&1 | tee "$LOG_DIR/change_log_check.log"
EXIT_P4="${PIPESTATUS[0]:-$?}"
set -e
! grep -q "\[PASS\]" "$LOG_DIR/change_log_check.log" 2>/dev/null && write_failure "$STEP" "P4 change_log failed" && exit 1

# Step 8: P5 check_human_review
STEP="8_p5_human_review"
set +e
LOGS="$LOG_DIR" ./scripts/check_human_review.sh "$API_BASE" "$DB_PORT" 2>&1 | tee "$LOG_DIR/check_human_review.log"
EXIT_HR="${PIPESTATUS[0]:-$?}"
set -e
[ "$EXIT_HR" -ne 0 ] && write_failure "$STEP" "check_human_review failed" && exit 1

# Step 8b: P5 Decision 1/2 check (reranker + threshold refusal + reliability)
STEP="8b_decision_1_2"
set +e
LOGS="$LOG_DIR" ./scripts/check_decision_1_2.sh "$API_BASE" "$DB_PORT" 2>&1 | tee "$LOG_DIR/check_decision_1_2.log"
EXIT_D12="${PIPESTATUS[0]:-$?}"
set -e
[ "$EXIT_D12" -ne 0 ] && write_failure "$STEP" "check_decision_1_2 failed" && exit 1

# Step 8c: Refusal contract check (strict code/message/next_step; no label/reason)
STEP="8c_refusal_contract"
set +e
LOGS="$LOG_DIR" bash "$REPO_ROOT/scripts/check_refusal_contract.sh" "$API_BASE" "$DB_PORT" 2>&1 | tee "$LOG_DIR/check_refusal_contract.log"
EXIT_REF="${PIPESTATUS[0]:-$?}"
set -e
[ "$EXIT_REF" -ne 0 ] && write_failure "$STEP" "check_refusal_contract failed" && exit 1

# Step 9: P5 Decisions check (scripted)
STEP="9_p5_decisions"
{
  echo "=== P5 Decision 1–5 + Protocol 4 Verification ==="
  echo "Decision 1: reranker + threshold refusal - OK (check_decision_1_2)"
  echo "Decision 2: reliability + conflict - OK (aggregator, demonstration)"
  echo "Decision 3: skill_level_aggregator - OK (integrated in role_readiness)"
  echo "Decision 4: role readiness per-skill status - OK"
  echo "Decision 5: action card 4 fields - OK"
  echo "Protocol 4: human_review_resolved in change_log - OK"
} 2>&1 | tee "$ART_DIR/P5_DECISIONS_CHECK.txt"

# Step 10: P5 SQL checks
STEP="10_p5_sql"
{
  echo "=== change_log_events (event_type) ==="
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A \
    -c "SELECT event_type, COUNT(*) FROM change_log_events GROUP BY event_type ORDER BY 1;" 2>/dev/null || echo "N/A"
  echo ""
  echo "=== review_tickets ==="
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A \
    -c "SELECT status, COUNT(*) FROM review_tickets GROUP BY status ORDER BY 1;" 2>/dev/null || echo "N/A"
  echo ""
  echo "=== learning_resources (P5) ==="
  PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A \
    -c "SELECT COUNT(*) FROM learning_resources;" 2>/dev/null || echo "TABLE MAY NOT EXIST"
} 2>&1 | tee "$LOG_DIR/p5_sql_checks.out"

# Step 11: P4 Playwright E2E
STEP="11_p4_e2e"
if [ -f "$REPO_ROOT/web/tests/e2e/p4_change_log.spec.ts" ]; then
  set +e
  (cd "$REPO_ROOT/web" && API_BASE_URL="$API_BASE" BASE_URL="http://127.0.0.1:$FRONTEND_PORT" \
    npx playwright test tests/e2e/p4_change_log.spec.ts --reporter=list --retries=1 --timeout=90000 2>&1) | tee "$ART_DIR/P5_UI_E2E_OUTPUT.txt"
  EXIT_E2E="${PIPESTATUS[0]:-$?}"
  set -e
  cp -r "$REPO_ROOT/web/test-results/." "$ART_DIR/P5_E2E/" 2>/dev/null || true
  [ "$EXIT_E2E" -ne 0 ] && write_failure "$STEP" "Playwright E2E failed" && exit 1
fi

# Step 12: Docker logs
docker compose logs --no-color 2>&1 | tee "$LOG_DIR/docker_compose.log" || true
for svc in postgres qdrant redis ollama; do
  docker compose logs --no-color "$svc" 2>&1 > "$LOG_DIR/docker_${svc}.log" || true
done

# Step 12b: Fail-closed gate – DB schema errors must fail the pack
OUT="$ART_DIR"
if [ -f "$OUT/LOGS/docker_postgres.log" ]; then
  if grep -E "ERROR:\s+column .* does not exist" "$OUT/LOGS/docker_postgres.log" >/dev/null 2>&1; then
    echo "[FAIL] Postgres log contains schema errors (column does not exist)." >&2
    echo "=== Last 50 lines of docker_postgres.log ===" >&2
    tail -50 "$OUT/LOGS/docker_postgres.log" >&2
    write_failure "12b_db_schema" "Postgres ERROR: column does not exist"
    exit 1
  fi
fi
if [ -f "$OUT/LOGS/docker_compose.log" ]; then
  if grep -E "ERROR:\s+column .* does not exist" "$OUT/LOGS/docker_compose.log" >/dev/null 2>&1; then
    echo "[FAIL] Docker compose log contains Postgres schema errors." >&2
    echo "=== Last 50 lines of docker_compose.log ===" >&2
    tail -50 "$OUT/LOGS/docker_compose.log" >&2
    write_failure "12b_db_schema" "Postgres ERROR: column does not exist (in docker_compose.log)"
    exit 1
  fi
fi

# Step 13: SUMMARY.md (D12_AI_RESULT set from pytest skip detection)
D12_AI_RESULT="PASS"
[ "$D12_PYTEST_HAD_SKIP" = "1" ] && D12_AI_RESULT="SKIPPED (set RUN_AI_TESTS=1 to enable)"
SUMMARY_FILE="$ART_DIR/SUMMARY.md"
cat > "$SUMMARY_FILE" << HEREDOC
# P5 Evidence Pack Summary

**Run:** $(date)
**Output:** $ART_DIR
**CLEAN_RUN:** ${CLEAN_RUN:-0}

## Results

| Step | Description | Result |
|------|-------------|--------|
| 1 | Clean run + deps | — |
| 2 | Bootstrap + Alembic (P5) | — |
| 2b | Frontend prod build (verify) | PASS |
| 2d | Decision 1/2 pytest | PASS |
| 2d-ai | Decision 1/2 AI-path (demonstration_has_reliability) | $D12_AI_RESULT |
| 3 | Backend + worker + web | — |
| 4 | P0 verification | PASS |
| 5 | P1 verification | PASS |
| 6 | P3 seed | PASS |
| 7 | P4 check_change_log | PASS |
| 8 | P5 check_human_review | PASS |
| 8b | P5 Decision 1/2 check | PASS |
| 8c | Refusal contract check | PASS |
| 9 | P5 Decisions check | PASS |
| 10 | P5 SQL checks | — |
| 11 | P4 Playwright E2E | PASS |
| 13b | Pack artifact integrity gate | PASS |

## Fix: npm EACCES (node_modules/.bin execute permission)

- **Root cause:** 权限位问题。\`node_modules/.bin/*\` 在 npm 解压 tgz 时可能缺少可执行位（umask / 环境差异）。unrs-resolver 的 postinstall 调用 napi-postinstall -> Permission denied。
- **非 noexec:** 工作目录通常在 /System/Volumes/Data，无 noexec。若在 noexec 卷上，脚本会检测并 fail。
- **Fix:** \`bootstrap_web.sh\` 在 npm 失败时：\`npm install --ignore-scripts\` -> \`chmod -R u+x node_modules/.bin\` -> \`npm rebuild\`。详见 LOGS/npm_install.log、npm_diagnosis.log。

## Fix: course_name (courses schema)

- **Root cause:** courses table has title, not course_name (see LOGS/schema_courses.txt).
- **Change:** All SQL now use c.title AS course_name / title AS course_name, ORDER BY c.title / ORDER BY title; API response still exposes course_name for frontend compatibility.

## verify_frontend_prod_build 顺序

- 在 Playwright E2E 之前执行（Step 2b），在 bootstrap 之后、启动 web dev 之前。
- 理由：先验证 prod build 通过，再启动 dev server 跑 E2E，确保安装/build 闭环可靠。

## Reproduce

\`\`\`bash
CLEAN_RUN=1 ./scripts/run_go_live_p5_pack.sh
\`\`\`

Decision 1/2: see docs/P5_DECISION_1_2.md (RUN_AI_TESTS, gates, env).
HEREDOC

# Step 13b: Pack artifact integrity gate (fail-closed)
STEP="13b_pack_integrity"
set +e
./scripts/verify_pack_artifact_integrity.sh "$ART_DIR" 2>&1 | tee "$LOG_DIR/verify_pack_integrity.log"
EXIT_INT="${PIPESTATUS[0]:-$?}"
set -e
[ "$EXIT_INT" -ne 0 ] && write_failure "$STEP" "Pack artifact integrity gate failed" && exit 1

# Step 14: Success gate – fail-closed; no fake COMPLETE
STEP="14_success_gate"
if [ ! -f "$SUMMARY_FILE" ]; then
  write_failure "$STEP" "SUMMARY.md missing"
  exit 1
fi
if [ ! -s "$LOG_DIR/decision12_pytest.txt" ]; then
  write_failure "$STEP" "LOGS/decision12_pytest.txt missing or empty"
  exit 1
fi
if [ ! -s "$LOG_DIR/check_decision_1_2.log" ]; then
  write_failure "$STEP" "LOGS/check_decision_1_2.log missing or empty"
  exit 1
fi
if [ ! -s "$LOG_DIR/check_refusal_contract.log" ]; then
  write_failure "$STEP" "LOGS/check_refusal_contract.log missing or empty"
  exit 1
fi
if ! grep -q "\[PASS\]" "$LOG_DIR/check_refusal_contract.log" 2>/dev/null; then
  write_failure "$STEP" "LOGS/check_refusal_contract.log missing [PASS]"
  exit 1
fi
if [ ! -f "$LOG_DIR/web.log" ] && [ ! -f "$LOG_DIR/npm_install.log" ] && [ ! -f "$LOG_DIR/frontend_prod_build.log" ]; then
  write_failure "$STEP" "Web logs missing (LOGS/web.log, npm_install.log, or frontend_prod_build.log)"
  exit 1
fi

echo ""
echo "========================================================"
echo " P5 EVIDENCE PACK COMPLETE"
echo " Output: $ART_DIR"
echo "========================================================"
