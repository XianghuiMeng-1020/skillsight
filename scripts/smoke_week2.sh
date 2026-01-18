#!/usr/bin/env bash
set -euo pipefail
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight}"

echo "== health =="; curl -sS http://127.0.0.1:8001/health; echo
echo "== stats ==";  curl -sS http://127.0.0.1:8001/stats; echo
echo "== routes (grep roles/skills) =="; curl -sS http://127.0.0.1:8001/__routes | grep -E '"/roles"|"/skills"' || true; echo

echo "== skills?q=HKU =="; curl -sS "http://127.0.0.1:8001/skills?q=HKU" | head -c 800; echo
echo "== roles ==";       curl -sS "http://127.0.0.1:8001/roles" | head -c 800; echo
echo "== role by id ==";  curl -sS "http://127.0.0.1:8001/roles/HKU.ROLE.ASSISTANT_PM.v1" | head -c 800; echo
