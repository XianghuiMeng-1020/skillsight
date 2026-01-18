#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_PY="backend/alembic/env.py"
cp "$ENV_PY" "$ENV_PY.bak.meta.$(date +%Y%m%d%H%M%S)"

python - <<'PY'
from pathlib import Path
import re

p = Path("backend/alembic/env.py")
s = p.read_text(encoding="utf-8")

# Replace the whole "Provide MetaData" block with a deterministic import
pattern = r"# ---- Provide MetaData for autogenerate ----.*?def get_url\(\) -> str:"
m = re.search(pattern, s, flags=re.S)
if not m:
    raise SystemExit("❌ Could not find metadata block in env.py (unexpected).")

replacement = """# ---- Provide MetaData for autogenerate ----
from backend.app.db.base import Base
target_metadata = Base.metadata

def get_url() -> str:
"""
s2 = re.sub(pattern, replacement, s, flags=re.S)
p.write_text(s2, encoding="utf-8")
print("✅ Locked target_metadata to backend.app.db.base:Base.metadata")
PY
