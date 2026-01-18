#!/usr/bin/env bash
set -e

API_BASE="${API_BASE:-http://localhost:8000}"

echo "Uploading demo files to $API_BASE ..."
echo ""

upload () {
  local file="$1"
  echo "Uploading: $file"
  curl -s -F "file=@$file" "$API_BASE/documents/upload"
  echo ""
  echo ""
}

upload "data/synthetic/synthetic_student_artifact.txt"
upload "data/synthetic/synthetic_no_privacy.txt"

echo "Done. Copy doc_id values above, then open:"
echo "  http://localhost:3000"
