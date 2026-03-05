#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== docker compose up =="
docker compose up -d

echo "== containers =="
docker ps | grep -E "skillsight_db|skillsight_redis" || true

echo "== basic probes =="
docker exec -i skillsight_redis redis-cli ping | grep PONG >/dev/null && echo "redis ok" || echo "redis NOT ok"
docker exec -i skillsight_db psql -U skillsight -d skillsight -c "select 1;" >/dev/null && echo "db ok" || echo "db NOT ok"

echo "OK: dev_up done"
