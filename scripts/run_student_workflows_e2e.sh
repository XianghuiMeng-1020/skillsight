#!/usr/bin/env bash
# 运行学生端全流程 E2E：模拟真实学生以多种顺序走通所有前端功能。
# 前置：后端 http://localhost:8001、前端 http://localhost:3000 已启动。
set -euo pipefail
cd "$(dirname "$0")/.."

API="${API_BASE_URL:-http://localhost:8001}"
FRONT="${NEXT_PUBLIC_FRONTEND_URL:-http://localhost:3000}"

echo "== Checking backend ($API) =="
if ! curl -sf --connect-timeout 3 "$API/health" >/dev/null 2>&1; then
  echo "WARN: Backend not reachable at $API/health. Upload/export steps may fail."
fi

echo "== Checking frontend ($FRONT) =="
if ! curl -sf --connect-timeout 3 "$FRONT" >/dev/null 2>&1; then
  echo "WARN: Frontend not reachable at $FRONT. Start with: cd web && npm run dev"
fi

echo "== Building frontend (production) =="
cd web
npm run build
echo "== Running student workflows E2E =="
# Use production build for stable runs (avoids dev-mode 500s)
API_BASE_URL="$API" NEXT_PUBLIC_FRONTEND_URL="$FRONT" E2E_USE_PROD=1 npx playwright test tests/e2e/student_workflows_full.spec.ts --reporter=list

echo "Done."
