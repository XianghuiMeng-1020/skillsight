#!/usr/bin/env bash
# SkillSight local quick-start (Docker Compose stack)
# Usage: ./scripts/start_local.sh
# Access: http://localhost:3000
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== SkillSight Local Start ==="

# 1) Ensure Docker Desktop is running
if ! docker info &>/dev/null; then
  echo "Starting Docker Desktop..."
  open -a Docker
  echo -n "Waiting for Docker"
  for i in {1..30}; do
    sleep 2
    docker info &>/dev/null && echo " ready." && break
    echo -n "."
    [ "$i" -eq 30 ] && echo "" && echo "ERROR: Docker did not start in 60s" && exit 1
  done
fi

# 2) Start all services (postgres, redis, qdrant, backend, frontend)
echo "== Starting containers =="
docker compose up -d

# 3) Wait for backend health
echo -n "Waiting for backend"
for i in {1..20}; do
  sleep 2
  STATUS=$(curl -s http://localhost:8001/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null || true)
  [ "$STATUS" = "ok" ] && echo " healthy." && break
  echo -n "."
  [ "$i" -eq 20 ] && echo "" && echo "WARNING: Backend health check timed out — check logs with: docker compose logs backend"
done

echo ""
echo "=== All services running ==="
echo "  Frontend : http://localhost:3000"
echo "  Backend  : http://localhost:8001"
echo "  API docs : http://localhost:8001/docs"
echo ""
echo "Login with any email address — first login auto-creates your account."
echo "To stop: docker compose down"
