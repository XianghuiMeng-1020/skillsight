#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8001}"

DOC_ID="${1:-}"
if [[ -z "$DOC_ID" ]]; then
  echo "usage: $0 <DOC_ID>"
  exit 2
fi

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

echo "API_BASE=$API_BASE"
echo "DOC_ID=$DOC_ID"
echo

curl -fsS "${API_BASE}/documents/${DOC_ID}/chunks?limit=200" -o "$TMP"

python3 - <<PY
import hashlib, json, sys
p = "${TMP}"
d = json.load(open(p))
items = d.get("items") if isinstance(d, dict) else d
assert isinstance(items, list) and items, "no chunks returned"

# pick first chunk for MVP verification (you can extend to random/all)
c = items[0]
qt = c.get("chunk_text")
qh = c.get("quote_hash")
assert isinstance(qt, str) and qt.strip() != "", "chunk_text missing/empty"
assert isinstance(qh, str) and qh.strip() != "", "quote_hash missing/empty"

calc = hashlib.sha256(qt.encode("utf-8", errors="ignore")).hexdigest()
print("chunk_id =", c.get("chunk_id"))
print("stored  =", qh)
print("calc    =", calc)

assert calc == qh, "quote_hash mismatch"
print("✅ quote_hash verified")
PY
