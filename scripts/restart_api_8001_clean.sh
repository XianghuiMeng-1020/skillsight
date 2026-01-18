#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8001}"

echo "🔎 Checking :$PORT listeners..."
PIDS="$(lsof -nP -iTCP:${PORT} -sTCP:LISTEN 2>/dev/null | awk 'NR>1{print $2}' | sort -u || true)"

if [ -n "${PIDS:-}" ]; then
  echo "🧹 Killing listeners on :$PORT -> ${PIDS}"
  # try graceful first
  for pid in $PIDS; do
    kill "$pid" 2>/dev/null || true
  done
  sleep 0.6
  # then force if still there
  PIDS2="$(lsof -nP -iTCP:${PORT} -sTCP:LISTEN 2>/dev/null | awk 'NR>1{print $2}' | sort -u || true)"
  if [ -n "${PIDS2:-}" ]; then
    echo "💥 Force killing -> ${PIDS2}"
    for pid in $PIDS2; do
      kill -9 "$pid" 2>/dev/null || true
    done
  fi
else
  echo "✅ :$PORT is free"
fi

echo "✅ Final check..."
lsof -nP -iTCP:${PORT} -sTCP:LISTEN >/dev/null 2>&1 && { echo "❌ still in use"; exit 1; } || echo "✅ :$PORT is free now"

# Ensure venv
if [ -f backend/.venv/bin/activate ]; then
  source backend/.venv/bin/activate
fi

# Ensure DATABASE_URL uses docker-mapped port (your current mapping)
export DATABASE_URL="postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight"

echo ""
echo "🧪 Sanity check DB wiring (should be 55432):"
python - <<'PY'
import os
print("DATABASE_URL =", os.getenv("DATABASE_URL"))
from backend.app.db import session
print("engine.url  =", session.engine.url)
PY

echo ""
echo "🚀 Starting uvicorn on :$PORT ..."
exec uvicorn backend.app.main:app --reload --port "$PORT"
