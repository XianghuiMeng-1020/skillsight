#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
ls -1 backend/alembic/versions | grep -E '^meta_check_tmp_.*\.py$' | while read -r f; do
  rm -f "backend/alembic/versions/$f"
  echo "🧹 removed backend/alembic/versions/$f"
done
echo "✅ cleanup done"
