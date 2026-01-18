#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/backend/.venv"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

echo "Repo: $ROOT"
if [ ! -x "$PY" ]; then
  echo "❌ backend/.venv not found. Creating..."
  python3 -m venv "$VENV"
fi

echo "Using python: $PY"
"$PY" -V

echo "Installing backend requirements..."
"$PIP" -q install -r backend/requirements.txt

echo "Check sqlalchemy import..."
"$PY" -c "import sqlalchemy; print('✅ sqlalchemy', sqlalchemy.__version__)"

echo "Check backend.app.main import..."
"$PY" -c "import backend.app.main as m; print('✅ import ok')"

echo "✅ doctor done"
