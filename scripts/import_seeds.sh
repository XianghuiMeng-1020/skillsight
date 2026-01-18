#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8001}"
BASE="http://127.0.0.1:${PORT}"

SKILLS_JSON="backend/data/seeds/skills.json"
ROLES_JSON="backend/data/seeds/roles.json"

if [ ! -f "$SKILLS_JSON" ]; then
  echo "❌ Missing $SKILLS_JSON"
  echo "   Put your skills seed at backend/data/seeds/skills.json"
  exit 1
fi
if [ ! -f "$ROLES_JSON" ]; then
  echo "❌ Missing $ROLES_JSON"
  echo "   Put your roles seed at backend/data/seeds/roles.json"
  exit 1
fi

echo "🔎 Checking backend health: $BASE/health"
curl -fsS "$BASE/health" >/dev/null
echo "✅ Backend is up"

# Try a set of possible import endpoints (your project evolved, so be defensive)
try_post_json () {
  local path="$1"
  local file="$2"
  local label="$3"
  echo "➡️  POST $path  ($label)"
  if curl -fsS -X POST "$BASE$path" -H "Content-Type: application/json" --data-binary "@$file" >/dev/null; then
    echo "✅ Imported $label via $path"
    return 0
  fi
  return 1
}

# Skills
if ! try_post_json "/skills/import" "$SKILLS_JSON" "skills"; then
  if ! try_post_json "/api/skills/import" "$SKILLS_JSON" "skills"; then
    echo "❌ Could not find a working skills import endpoint."
    echo "   Try: curl -s $BASE/docs and tell me your real route name."
    exit 1
  fi
fi

# Roles
if ! try_post_json "/roles/import" "$ROLES_JSON" "roles"; then
  if ! try_post_json "/api/roles/import" "$ROLES_JSON" "roles"; then
    echo "❌ Could not find a working roles import endpoint."
    echo "   Try: curl -s $BASE/docs and tell me your real route name."
    exit 1
  fi
fi

echo ""
echo "✅ Seeds imported."
echo "Try:"
echo "  curl -s '$BASE/skills?q=' | head"
echo "  curl -s '$BASE/roles' | head"
