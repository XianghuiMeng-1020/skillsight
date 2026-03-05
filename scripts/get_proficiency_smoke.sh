#!/usr/bin/env bash
set -euo pipefail

DOC_ID="${1:-}"
if [ -z "$DOC_ID" ]; then
  echo "usage: $0 <doc_id>"
  exit 2
fi

API_BASE="${API_BASE:-http://127.0.0.1:8001}"
echo "API_BASE=$API_BASE"
echo "DOC_ID=$DOC_ID"

TMP="$(mktemp)"

echo
echo "== get proficiency (latest_per_skill=true) =="
curl -fsS "${API_BASE}/proficiency?doc_id=${DOC_ID}&latest_per_skill=true&limit=200" -o "$TMP"

python3 - <<PY
import json
d=json.load(open("$TMP"))
print("keys=", sorted(list(d.keys())))
print("doc_id=", d.get("doc_id"))
print("count=", d.get("count"))
items=d.get("items") or []
print("items_n=", len(items))
if items:
    print("first_keys=", sorted(list(items[0].keys())))
    for it in items[:10]:
        print("-", it.get("skill_id"), "level=", it.get("level"), "label=", it.get("label"))
PY

rm -f "$TMP"
echo
echo "proficiency smoke ok"
