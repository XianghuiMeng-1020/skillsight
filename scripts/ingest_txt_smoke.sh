#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8001}"
FILE="${1:-samples/sample_doc.txt}"

echo "API_BASE=$API_BASE"
echo "FILE=$FILE"

if [[ ! -f "$FILE" ]]; then
  echo "❌ file not found: $FILE"
  exit 1
fi

echo
echo "== import =="
# expects POST /documents/import multipart file param name: file
RESP="$(curl -fsS -X POST "${API_BASE}/documents/import" -F "file=@${FILE}" )"
echo "$RESP" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("doc_id=", d.get("doc_id") or d.get("id") or d.get("document",{}).get("doc_id"))'
DOC_ID="$(echo "$RESP" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("doc_id") or d.get("id") or d.get("document",{}).get("doc_id") or "")')"

if [[ -z "$DOC_ID" ]]; then
  echo "❌ cannot parse doc_id from response"
  echo "$RESP"
  exit 1
fi

echo
echo "== verify documents has it =="
curl -fsS "${API_BASE}/documents/${DOC_ID}" >/dev/null
echo "✅ document fetch ok: $DOC_ID"

echo
echo "== verify chunks by doc > 0 =="
CNT="$(curl -fsS "${API_BASE}/documents/${DOC_ID}/chunks" | python3 -c 'import json,sys; d=json.load(sys.stdin); 
items=d.get("items") if isinstance(d,dict) else d; 
print(len(items) if isinstance(items,list) else (d.get("count") or 0))')"
echo "doc chunks count=$CNT"

python3 - <<PY
cnt=int("$CNT")
assert cnt>0, "expected chunks > 0"
print("✅ chunks > 0")
PY

echo
echo "✅ ingest smoke ok"
