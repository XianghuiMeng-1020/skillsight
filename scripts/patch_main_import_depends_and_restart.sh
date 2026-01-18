#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from pathlib import Path
import re, datetime

p = Path("backend/app/main.py")
s = p.read_text(encoding="utf-8")
bak = p.with_suffix(p.suffix + f".bak.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}")
bak.write_text(s, encoding="utf-8")

# 1) Ensure Depends is importable
# Try to add Depends into an existing "from fastapi import ..." line
m = re.search(r"(?m)^from fastapi import ([^\n]+)$", s)
if m:
    items = [x.strip() for x in m.group(1).split(",")]
    if "Depends" not in items:
        items.append("Depends")
        items = sorted(set(items), key=lambda x: x.lower())
        new_line = "from fastapi import " + ", ".join(items)
        s = re.sub(r"(?m)^from fastapi import ([^\n]+)$", new_line, s, count=1)
else:
    # Else add a standalone import
    if "from fastapi import Depends" not in s:
        # Insert near the top after other imports
        lines = s.splitlines(True)
        i = 0
        while i < len(lines) and (lines[i].startswith("import ") or lines[i].startswith("from ")):
            i += 1
        lines.insert(i, "from fastapi import Depends\n")
        s = "".join(lines)

p.write_text(s, encoding="utf-8")
print(f"✅ Patched {p} to ensure Depends import. backup: {bak.name}")
PY

# 2) Restart server cleanly and smoke
mkdir -p logs
lsof -ti tcp:8001 | xargs -r kill -9 || true

export DATABASE_URL="postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight"
nohup uvicorn backend.app.main:app --port 8001 > logs/uvicorn_8001.log 2>&1 &
sleep 1

echo "== Smoke =="
curl -sS http://127.0.0.1:8001/health && echo
curl -sS http://127.0.0.1:8001/__routes | head -c 400 && echo
curl -sS "http://127.0.0.1:8001/roles/HKU.ROLE.ASSISTANT_PM.v1" | head -c 900 && echo

echo
echo "== Tail log =="
tail -n 60 logs/uvicorn_8001.log
