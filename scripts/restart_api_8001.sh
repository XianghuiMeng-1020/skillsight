#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PORT="${PORT:-8001}"
HOST="${HOST:-127.0.0.1}"
API_BASE="http://${HOST}:${PORT}"
LOG_FILE="${LOG_FILE:-logs/uvicorn_${PORT}.log}"

echo "== restart api =="
echo "ROOT_DIR=$ROOT_DIR"
echo "HOST=$HOST"
echo "PORT=$PORT"
echo "API_BASE=$API_BASE"
echo "LOG_FILE=$LOG_FILE"

# 1) Ensure backend env exists
if [[ ! -f "backend/.env" ]]; then
  echo "❌ backend/.env not found"
  exit 1
fi

echo
echo "== backend/.env (DATABASE_URL) =="
grep -E '^DATABASE_URL=' backend/.env || true

# 2) Kill anything listening on PORT
echo
echo "== kill existing listener on :$PORT (if any) =="
PIDS="$(lsof -nP -iTCP:${PORT} -sTCP:LISTEN 2>/dev/null | awk 'NR>1{print $2}' | sort -u || true)"
if [[ -n "${PIDS}" ]]; then
  echo "found pids: ${PIDS}"
  for pid in ${PIDS}; do
    echo "killing pid=$pid"
    kill -9 "$pid" || true
  done
else
  echo "no listener found"
fi

# 3) Start uvicorn in background
echo
echo "== start uvicorn (background) =="
mkdir -p "$(dirname "$LOG_FILE")"
: > "$LOG_FILE"

# Avoid leaking terminal env vars into app (common pitfall)
unset DB_URL || true

# Start
nohup ./backend/.venv/bin/uvicorn backend.app.main:app --host "$HOST" --port "$PORT" >"$LOG_FILE" 2>&1 &
UV_PID=$!

echo "uvicorn pid=$UV_PID"
echo "tail -f $LOG_FILE"

# 4) Wait for /health
echo
echo "== wait for health =="
OK=0
for i in $(seq 1 60); do
  if curl -fsS "${API_BASE}/health" >/dev/null 2>&1; then
    OK=1
    break
  fi
  sleep 0.3
done

if [[ "$OK" != "1" ]]; then
  echo "❌ health check failed: ${API_BASE}/health"
  echo
  echo "== last 120 lines of log =="
  tail -n 120 "$LOG_FILE" || true
  exit 1
fi

echo "✅ api is up: ${API_BASE}"
