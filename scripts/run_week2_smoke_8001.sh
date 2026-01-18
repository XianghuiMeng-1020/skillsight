#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8001}"
DBURL="${DATABASE_URL:-postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight}"

echo "🔎 Checking :$PORT..."

# Kill anything listening on PORT
PID_LIST="$(lsof -nP -iTCP:${PORT} -sTCP:LISTEN 2>/dev/null | awk 'NR>1{print $2}' | sort -u || true)"
if [ -n "${PID_LIST:-}" ]; then
  echo "🧹 Killing processes on :$PORT -> ${PID_LIST}"
  for pid in $PID_LIST; do
    kill -9 "$pid" 2>/dev/null || true
  done
  sleep 0.5
fi

mkdir -p logs

# Ensure venv is active enough (best-effort)
if [ -f "backend/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source backend/.venv/bin/activate
fi

export DATABASE_URL="$DBURL"
echo "✅ DATABASE_URL=$DATABASE_URL"

LOG="logs/uvicorn_${PORT}.log"
echo "🚀 Starting uvicorn on :$PORT (log -> $LOG)"
# Start in background (no --reload to avoid reloader double-process issues)
nohup uvicorn backend.app.main:app --port "$PORT" > "$LOG" 2>&1 &
UVPID=$!
echo "✅ uvicorn pid=$UVPID"

# Wait for health
echo "⏳ Waiting for /health ..."
ok=0
for i in $(seq 1 40); do
  if curl -sS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 0.25
done

if [ "$ok" -ne 1 ]; then
  echo "❌ Backend did not become healthy. Tail log:"
  tail -n 80 "$LOG" || true
  exit 1
fi

echo "✅ /health OK"

echo ""
echo "== /__routes (head) =="
curl -sS "http://127.0.0.1:${PORT}/__routes" | head -c 1200; echo
echo ""
echo "== /skills?q= (head) =="
curl -sS "http://127.0.0.1:${PORT}/skills?q=" | head -c 1200; echo
echo ""
echo "== /roles (head) =="
curl -sS "http://127.0.0.1:${PORT}/roles" | head -c 1200; echo
echo ""
echo "✅ Smoke done. Full uvicorn log: $LOG"
