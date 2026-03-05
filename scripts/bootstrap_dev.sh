#!/usr/bin/env bash
# Bootstrap dev environment: venv, backend deps, web deps, docker compose, alembic upgrade head.
# Usage: ./scripts/bootstrap_dev.sh [REPO_ROOT]
# Run from repo root or pass REPO_ROOT. Creates venv at REPO_ROOT/venv (or backend/venv if preferred).
set -euo pipefail

REPO_ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$REPO_ROOT"

echo "== Bootstrap dev @ $REPO_ROOT =="

# 1) venv
VENV_DIR="${VENV_DIR:-$REPO_ROOT/venv}"
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating venv at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi
# Activate for this script so we can run pip/alembic
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# 2) backend deps
echo "== Installing backend deps =="
pip install -q -r "$REPO_ROOT/backend/requirements.txt"

# 3) web deps
if [ -f "$REPO_ROOT/web/package.json" ]; then
  echo "== Installing web deps =="
  LOG_DIR="${LOG_DIR:-$REPO_ROOT/artifacts/LOGS}" "$REPO_ROOT/scripts/bootstrap_web.sh" "$REPO_ROOT" "${LOG_DIR:-}"
fi

# 4) docker compose (deps only: postgres, redis, qdrant, ollama)
echo "== Starting docker compose =="
docker compose up -d

# 5) Wait for postgres
echo "== Waiting for Postgres =="
DB_PORT="${DB_PORT:-55432}"
for i in {1..30}; do
  if PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -c "select 1;" 2>/dev/null; then
    break
  fi
  [ "$i" -eq 30 ] && { echo "Postgres did not become ready"; exit 1; }
  sleep 1
done
echo "Postgres ready."

# 6) alembic upgrade head (from repo root with backend as cwd for alembic.ini)
echo "== Alembic upgrade head =="
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://skillsight:skillsight@127.0.0.1:$DB_PORT/skillsight}"
(cd "$REPO_ROOT/backend" && PYTHONPATH="$REPO_ROOT" python -m alembic upgrade head)

# 7) Create skillsight_test and run alembic for pytest
echo "== Creating skillsight_test and running alembic =="
PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d postgres -c "CREATE DATABASE skillsight_test;" 2>/dev/null || true
export DATABASE_URL="postgresql+psycopg2://skillsight:skillsight@127.0.0.1:$DB_PORT/skillsight_test"
(cd "$REPO_ROOT/backend" && PYTHONPATH="$REPO_ROOT" python -m alembic upgrade head)

echo ""
echo "Bootstrap complete. Activate venv: source $VENV_DIR/bin/activate"
echo "Then start backend (e.g. uvicorn), worker, and web as needed."
