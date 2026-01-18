#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from pathlib import Path
import datetime

p = Path("backend/app/main.py")
s = p.read_text(encoding="utf-8")

bak = p.with_suffix(p.suffix + f".bak.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}")
bak.write_text(s, encoding="utf-8")

# Fix bad patches that injected \"\"\" docstrings (or any escaped quotes) at top-level code.
# Convert all \" -> " (these were not intended escapes in source).
s2 = s.replace('\\"', '"')

p.write_text(s2, encoding="utf-8")
print(f"✅ Fixed escaped quotes in {p}. backup: {bak.name}")
PY

mkdir -p logs
lsof -ti tcp:8001 | xargs -r kill -9 || true

export DATABASE_URL="postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight"
nohup uvicorn backend.app.main:app --port 8001 > logs/uvicorn_8001.log 2>&1 &
sleep 1

echo "== Smoke =="
curl -sS http://127.0.0.1:8001/health && echo
curl -sS http://127.0.0.1:8001/__routes | head -c 500 && echo
curl -sS "http://127.0.0.1:8001/roles/HKU.ROLE.ASSISTANT_PM.v1" | head -c 900 && echo
curl -sS "http://127.0.0.1:8001/skills?q=HKU" | head -c 900 && echo

echo
echo "== Tail log =="
tail -n 80 logs/uvicorn_8001.log
