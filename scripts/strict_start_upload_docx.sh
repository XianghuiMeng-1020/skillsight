#!/usr/bin/env bash
set -e

API_BASE="${API_BASE:-http://localhost:8000}"
SUBJECT_ID="${SUBJECT_ID:-student_demo}"
SCOPE="${SCOPE:-analysis}"
DOC_TYPE="${DOC_TYPE:-synthetic}"
FILE_PATH="${1:-data/synthetic/demo_week9.docx}"

if [ ! -f "$FILE_PATH" ]; then
  echo "ERROR: file not found: $FILE_PATH"
  exit 1
fi

echo "[1/2] consent/start..."
START_JSON=$(curl -s -X POST "$API_BASE/consent/start" -H "Content-Type: application/json" -d "{\"subject_id\":\"$SUBJECT_ID\",\"scope\":\"$SCOPE\"}")
DOC_ID=$(python3 - <<PY2
import json,sys
o=json.loads(sys.argv[1])
print(o["doc_id"])
PY2
"$START_JSON")
TOKEN=$(python3 - <<PY2
import json,sys
o=json.loads(sys.argv[1])
print(o["upload_token"])
PY2
"$START_JSON")

echo "doc_id=$DOC_ID"
echo "upload_token=$TOKEN"

echo "[2/2] uploading $FILE_PATH ..."
curl -s -F "doc_id=$DOC_ID" \
     -F "upload_token=$TOKEN" \
     -F "subject_id=$SUBJECT_ID" \
     -F "doc_type=$DOC_TYPE" \
     -F "file=@$FILE_PATH" \
     "$API_BASE/documents/upload"

echo ""
echo "OK. Open frontend and use doc_id:"
echo "  $DOC_ID"
