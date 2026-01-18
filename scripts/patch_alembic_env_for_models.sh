#!/usr/bin/env bash
set -euo pipefail

ROOT="$(pwd)"
ENV_PY="$ROOT/backend/alembic/env.py"
if [[ ! -f "$ENV_PY" ]]; then
  echo "❌ Alembic env.py not found at: $ENV_PY"
  exit 1
fi

cp "$ENV_PY" "${ENV_PY}.bak.$(date -u +%Y%m%d%H%M%S)"

python - <<'PY'
from pathlib import Path
p = Path("backend/alembic/env.py")
txt = p.read_text(encoding="utf-8")

# Ensure sys.path includes repo root (so `backend` package import works)
if "sys.path.append" not in txt and "sys.path.insert" not in txt:
    inject = (
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[2]\n"
        "sys.path.insert(0, str(ROOT))\n\n"
    )
    # Put after imports header (best-effort)
    if "from logging.config import fileConfig" in txt:
        txt = txt.replace("from logging.config import fileConfig\n", "from logging.config import fileConfig\n" + inject)
    else:
        txt = inject + txt

# Force metadata binding to our Base
# Add imports for Base + models registration
marker = "target_metadata"
if marker in txt:
    # Ensure these lines exist somewhere above target_metadata assignment
    if "from backend.app.db.base import Base" not in txt:
        txt = txt.replace("from alembic import context\n", "from alembic import context\nfrom backend.app.db.base import Base\nimport backend.app.models  # noqa: F401  (register tables)\n")
    # Replace target_metadata assignment
    import re
    txt = re.sub(r"target_metadata\s*=\s*.*", "target_metadata = Base.metadata", txt)
else:
    # If env.py is nonstandard, append safe block
    txt += "\nfrom backend.app.db.base import Base\nimport backend.app.models  # noqa: F401\n"
    txt += "target_metadata = Base.metadata\n"

p.write_text(txt, encoding="utf-8")
print("✅ Patched backend/alembic/env.py")
PY
