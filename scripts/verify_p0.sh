#!/usr/bin/env bash
# Verify P0: pytest, alembic upgrade head (from empty DB optional), e2e_golden_path.
# Usage: ./scripts/verify_p0.sh [API_BASE] [DB_PORT]
# Expects: venv activated, docker compose deps up, DATABASE_URL set.
# Set VERIFY_EMPTY_DB=1 to run alembic from empty DB (drops all; destructive).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

API_BASE="${1:-http://127.0.0.1:8001}"
DB_PORT="${2:-55432}"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://skillsight:skillsight@127.0.0.1:${DB_PORT}/skillsight}"

PYTHON_BIN="${PYTHON_BIN:-python}"
[ -f "$REPO_ROOT/.venv/bin/python" ] && PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
[ -f "$REPO_ROOT/venv/bin/python" ] && PYTHON_BIN="$REPO_ROOT/venv/bin/python"

echo "=== P0 Verification ==="
echo "API_BASE=$API_BASE DB_PORT=$DB_PORT"
echo ""

# 1) pytest
echo "[1/3] pytest"
(cd "$REPO_ROOT/backend" && PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" -m pytest tests/ -v --tb=short) || { echo "FAIL: pytest"; exit 1; }
echo "  OK"
echo ""

# 2) alembic upgrade head (optional from empty DB)
if [ "${VERIFY_EMPTY_DB:-0}" = "1" ]; then
  echo "[2/3] alembic upgrade head (empty DB simulation)"
  (cd "$REPO_ROOT/backend" && PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" -m alembic upgrade head) || { echo "FAIL: alembic"; exit 1; }
  echo "  OK"
else
  echo "[2/3] alembic upgrade head (current DB)"
  (cd "$REPO_ROOT/backend" && PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" -m alembic upgrade head) || { echo "FAIL: alembic"; exit 1; }
  echo "  OK"
fi
echo ""

# 3) e2e golden path
echo "[3/3] e2e_golden_path.sh"
"$REPO_ROOT/scripts/e2e_golden_path.sh" "$API_BASE" "$DB_PORT" || { echo "FAIL: e2e_golden_path"; exit 1; }
echo "  OK"
echo ""

echo "=========================================="
echo "PASS"
echo "=========================================="
