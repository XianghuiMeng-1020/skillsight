#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
F="backend/app/db/session.py"

if [ ! -f "$ROOT/$F" ]; then
  echo "❌ Not found: $F"
  exit 1
fi

TS="$(date +%Y%m%d%H%M%S)"
cp "$ROOT/$F" "$ROOT/$F.bak.$TS"

python3 - <<'PY'
from pathlib import Path
import re, datetime

p = Path("backend/app/db/session.py")
s = p.read_text(encoding="utf-8")

# Ensure python-dotenv dependency exists in requirements (best effort, no fail)
req = Path("backend/requirements.txt")
if req.exists():
    r = req.read_text(encoding="utf-8")
    if "python-dotenv" not in r:
        req.write_text(r.rstrip() + "\npython-dotenv>=1.0\n", encoding="utf-8")
        print("✅ ensured python-dotenv in backend/requirements.txt")

# Insert robust DB URL loader block near top after imports.
# We will:
# 1) load backend/.env if present (without overriding existing env vars)
# 2) require DATABASE_URL or SQLALCHEMY_DATABASE_URL
# 3) create engine from that; no silent localhost:5432 fallback
loader_block = r'''
# --- DB URL resolution (locked) ---
import os
from pathlib import Path as _Path
try:
    # Load backend/.env if present, but do not override already-exported env vars.
    from dotenv import load_dotenv  # type: ignore
    _env_path = (_Path(__file__).resolve().parents[2] / ".env")  # backend/.env
    if _env_path.exists():
        load_dotenv(dotenv_path=str(_env_path), override=False)
except Exception:
    # dotenv is optional; env vars may be provided by shell/docker
    pass

DB_URL = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URL")
if not DB_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Set it in your shell or put it in backend/.env. "
        "Example: postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight"
    )
# --- end DB URL resolution ---
'''.strip("\n")

# Try to locate create_engine import line; we'll inject after SQLAlchemy imports.
# If already patched (DB_URL exists), just update the DB_URL logic and remove old fallback if present.
if "DB_URL = os.getenv(\"DATABASE_URL\")" in s and "raise RuntimeError" in s:
    print("ℹ️ session.py already has locked DB_URL block; leaving as-is.")
    p.write_text(s, encoding="utf-8")
    raise SystemExit(0)

# Add loader_block after SQLAlchemy imports block
# Find last import line before first non-import statement.
lines = s.splitlines()
insert_at = 0
for i, line in enumerate(lines):
    if line.startswith("import ") or line.startswith("from "):
        insert_at = i + 1
    elif line.strip() == "":
        continue
    else:
        break
lines.insert(insert_at, loader_block)

s2 = "\n".join(lines)

# Now replace any create_engine(...) DSN that hardcodes localhost:5432 or reads a local constant.
# Common patterns: create_engine(SQLALCHEMY_DATABASE_URL) or create_engine(DATABASE_URL) or create_engine("postgresql...")
# We'll prefer create_engine(DB_URL, ...)
s2 = re.sub(r'create_engine\(\s*["\'][^"\']+["\']\s*([,\)])', r'create_engine(DB_URL\1', s2)
s2 = re.sub(r'create_engine\(\s*(SQLALCHEMY_DATABASE_URL|DATABASE_URL)\s*([,\)])', r'create_engine(DB_URL\2', s2)

# If there's a line like SQLALCHEMY_DATABASE_URL = "postgresql+psycopg2://...5432..."
s2 = re.sub(r'^\s*(SQLALCHEMY_DATABASE_URL|DATABASE_URL)\s*=\s*["\'].*5432.*["\']\s*$', '', s2, flags=re.M)

# Clean up multiple blank lines
s2 = re.sub(r'\n{3,}', '\n\n', s2).strip() + "\n"

p.write_text(s2, encoding="utf-8")
print("✅ Patched backend/app/db/session.py to lock DB URL (no silent fallback).")
PY

echo "✅ patch_dburl_lock done."
echo "Backup: $F.bak.$TS"
echo ""
echo "Next:"
echo "  source backend/.venv/bin/activate"
echo "  pip install -r backend/requirements.txt"
echo "  export DATABASE_URL='postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight'"
echo "  uvicorn backend.app.main:app --reload --port 8001"
echo "  python - <<'PY'"
echo "  import os; print(os.getenv('DATABASE_URL'))"
echo "  from backend.app.db import session; print('engine.url=', session.engine.url)"
echo "  PY"
