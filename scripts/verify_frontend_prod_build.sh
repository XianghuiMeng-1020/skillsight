#!/usr/bin/env bash
# Verify frontend production build: npm ci, build, (optional) lint.
# Fail-closed: any step fails -> exit 1.
# Bash 3.2 compatible.
#
# Usage: LOG_DIR=/path ./scripts/verify_frontend_prod_build.sh [REPO_ROOT]
# Output: artifacts/.../LOGS/frontend_prod_build.log
set -e
set -u
set +o pipefail 2>/dev/null || true

REPO_ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
WEB_DIR="$REPO_ROOT/web"
LOG_DIR="${LOG_DIR:-$REPO_ROOT/artifacts/LOGS}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/frontend_prod_build.log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== verify_frontend_prod_build $(date) ==="

if [ ! -f "$WEB_DIR/package.json" ]; then
  echo "[FAIL] No web/package.json"
  exit 1
fi

# [1/3] Install via bootstrap_web (handles EACCES workaround)
echo "[1/3] Web deps (bootstrap_web)"
LOG_DIR="$LOG_DIR" "$REPO_ROOT/scripts/bootstrap_web.sh" "$REPO_ROOT" "$LOG_DIR" || { echo "[FAIL] bootstrap_web failed"; exit 1; }

cd "$WEB_DIR"
echo "[2/3] npm run build"
npm run build

if grep -q '"lint"' package.json 2>/dev/null; then
  echo "[3/3] npm run lint (optional)"
  if ! npm run lint; then
    echo "[WARN] lint failed (non-blocking; optional step)"
  fi
else
  echo "[3/3] npm run lint - not defined, skip"
fi

echo "[PASS] Frontend prod build OK"
