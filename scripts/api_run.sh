#!/usr/bin/env bash
set -euo pipefail

mkdir -p logs
lsof -ti tcp:8001 | xargs -r kill -9 || true

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight}"
nohup uvicorn backend.app.main:app --port 8001 > logs/uvicorn_8001.log 2>&1 &

sleep 1
echo "✅ backend up?"
curl -sS http://127.0.0.1:8001/health && echo
