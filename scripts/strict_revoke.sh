#!/usr/bin/env bash
set -e

API_BASE="${API_BASE:-http://localhost:8000}"
SUBJECT_ID="${SUBJECT_ID:-student_demo}"

DOC_ID="${1:-}"
TOKEN="${2:-}"

if [ -z "$DOC_ID" ] || [ -z "$TOKEN" ]; then
  echo "Usage: ./scripts/strict_revoke.sh <doc_id> <upload_token>"
  exit 1
fi

echo "Revoking consent and deleting doc..."
curl -s -X POST "$API_BASE/consent/revoke" \
  -H "Content-Type: application/json" \
  -d "{\"doc_id\":\"$DOC_ID\",\"subject_id\":\"$SUBJECT_ID\",\"upload_token\":\"$TOKEN\",\"reason\":\"script_revoke\"}"

echo ""
echo "Check chunks access (should be 403/404):"
curl -s -i "$API_BASE/documents/$DOC_ID/chunks?limit=1" | head -n 5
