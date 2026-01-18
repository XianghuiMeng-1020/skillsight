#!/usr/bin/env bash
set -e

PORT=8000

echo "Killing processes on port $PORT..."
lsof -nP -iTCP:$PORT -sTCP:LISTEN | awk 'NR>1 {print $2}' | xargs -r kill -9 || true

echo "Killing any uvicorn reload workers (best-effort)..."
pkill -f "uvicorn app.main:app" || true

echo "Starting backend..."
cd backend
source .venv/bin/activate
exec uvicorn app.main:app --reload --port 8000
