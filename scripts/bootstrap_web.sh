#!/usr/bin/env bash
# Web Bootstrap Gate – npm install with EACCES workaround (macOS / bash 3.2)
#
# Root cause: node_modules/.bin scripts may lack execute permission when npm extracts
# (umask / tgz extraction). Fix: npm ci/install, chmod only when needed.
#
# Usage: bash "$ROOT_DIR/scripts/bootstrap_web.sh" [ARTIFACTS_DIR]
#   ARTIFACTS_DIR: pack output dir (e.g. artifacts/go_live_baseline_p5/YYYYMMDD_HHMMSS)
#   Logs go to ARTIFACTS_DIR/LOGS or artifacts/LOGS if not passed.
# Fails closed: exit 1 on any error. Works from any cwd (uses BASH_SOURCE).
set -e
set -u
set -o pipefail 2>/dev/null || true

# BASH_SOURCE works in bash 3.0+; fallback to $0 for other shells
_SCRIPT="${BASH_SOURCE[0]:-$0}"
ROOT_DIR="$(cd "$(dirname "$_SCRIPT")/.." && pwd)"
cd "$ROOT_DIR/web"

# Resolve LOG_DIR: arg2=LOG_DIR (bootstrap_dev), arg1=ARTIFACTS_DIR or REPO_ROOT
if [ -n "${2:-}" ]; then
  LOG_DIR="$2"
elif [ -n "${1:-}" ]; then
  if [ -d "$1/web" ]; then
    LOG_DIR="$1/artifacts/LOGS"
  else
    case "$1" in
      *LOGS) LOG_DIR="$1" ;;
      *)     LOG_DIR="$1/LOGS" ;;
    esac
  fi
else
  LOG_DIR="${LOG_DIR:-$ROOT_DIR/artifacts/LOGS}"
fi
case "$LOG_DIR" in
  /*) ;;
  *) LOG_DIR="$ROOT_DIR/$LOG_DIR" ;;
esac
mkdir -p "$LOG_DIR"

NPM_LOG="$LOG_DIR/npm_install.log"
DIAG_LOG="$LOG_DIR/npm_diagnosis.log"
WEB_LOG="$LOG_DIR/web.log"

# Diagnostic output (always run, append to log)
{
  echo "=== bootstrap_web $(date) ==="
  echo "node -v: $(node -v 2>/dev/null || echo 'node not found')"
  echo "npm -v: $(npm -v 2>/dev/null || echo 'npm not found')"
  echo "pwd: $(pwd)"
  echo ""
  echo "=== ls -la ==="
  ls -la
  echo ""
  if [ -d "node_modules/.bin" ]; then
    echo "=== ls -la node_modules/.bin | head -50 ==="
    ls -la node_modules/.bin 2>/dev/null | head -50
  else
    echo "=== node_modules/.bin: not found ==="
  fi
} >> "$WEB_LOG" 2>&1
cat "$WEB_LOG" | tail -80

if [ ! -f "package.json" ]; then
  echo "[bootstrap_web] No web/package.json" >&2
  exit 1
fi

# Prefer npm ci if package-lock.json exists
USE_CI=0
if [ -f "package-lock.json" ]; then
  USE_CI=1
fi

echo "[bootstrap_web] Installing web deps @ $(pwd)"
NPM_EXIT=0
if [ "$USE_CI" = "1" ]; then
  npm ci >> "$NPM_LOG" 2>&1 || NPM_EXIT=$?
else
  npm install >> "$NPM_LOG" 2>&1 || NPM_EXIT=$?
fi

if [ ! -d "node_modules" ]; then
  echo "[bootstrap_web] node_modules missing after npm install" >&2
  echo "=== npm install log tail ===" >&2
  tail -120 "$NPM_LOG" >&2
  exit 1
fi

if [ "$NPM_EXIT" -ne 0 ]; then
  if grep -qE "Permission denied|EACCES|code 126" "$NPM_LOG" 2>/dev/null; then
    echo "[bootstrap_web] Permission error, retrying with --ignore-scripts + chmod + rebuild" >&2
    rm -rf node_modules
    if [ "$USE_CI" = "1" ]; then
      npm ci --ignore-scripts >> "$NPM_LOG" 2>&1 || { echo "[bootstrap_web] npm ci --ignore-scripts failed" >&2; tail -120 "$NPM_LOG" >&2; exit 1; }
    else
      npm install --ignore-scripts >> "$NPM_LOG" 2>&1 || { echo "[bootstrap_web] npm install --ignore-scripts failed" >&2; tail -120 "$NPM_LOG" >&2; exit 1; }
    fi
    if [ ! -d "node_modules" ]; then
      echo "[bootstrap_web] node_modules still missing" >&2
      tail -120 "$NPM_LOG" >&2
      exit 1
    fi
    [ -d "node_modules/.bin" ] && chmod -R u+x node_modules/.bin
    npm rebuild >> "$NPM_LOG" 2>&1 || { echo "[bootstrap_web] npm rebuild failed" >&2; tail -80 "$NPM_LOG" >&2; exit 1; }
  else
    echo "[bootstrap_web] npm install failed" >&2
    tail -120 "$NPM_LOG" >&2
    exit 1
  fi
fi

# chmod only when .bin exists AND has files missing execute bit
if [ -d "node_modules/.bin" ]; then
  NEED_CHMOD=0
  for f in node_modules/.bin/*; do
    if [ -e "$f" ]; then
      if [ -f "$f" ] && [ ! -x "$f" ]; then
        NEED_CHMOD=1
        break
      fi
      if [ -L "$f" ]; then
        TGT="$(readlink "$f" 2>/dev/null || true)"
        if [ -n "$TGT" ]; then
          TGT_PATH="node_modules/.bin/$TGT"
          if [ -f "$TGT_PATH" ] && [ ! -x "$TGT_PATH" ]; then
            NEED_CHMOD=1
            break
          fi
        fi
      fi
    fi
  done
  if [ "$NEED_CHMOD" = "1" ]; then
    chmod -R u+x node_modules/.bin
  fi
fi

# Final diagnostic
if [ -d "node_modules/.bin" ]; then
  echo "=== ls -la node_modules/.bin | head -50 ===" >> "$WEB_LOG"
  ls -la node_modules/.bin 2>/dev/null | head -50 >> "$WEB_LOG"
fi

echo "[bootstrap_web] Web deps OK."
