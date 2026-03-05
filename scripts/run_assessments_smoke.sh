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
echo "== run assessments =="
curl -fsS -X POST "${API_BASE}/assessments/run?doc_id=${DOC_ID}" -o "$TMP"

python3 - <<PY
import json
d=json.load(open("$TMP"))
print("keys=", sorted(list(d.keys())))
print("run_id=", d.get("run_id"))
print("rule_version=", d.get("rule_version"))
print("doc_id=", d.get("doc_id"))
print("skills_evaluated=", d.get("skills_evaluated"))
res=d.get("results") or []
print("results_n=", len(res))
if res:
    print("first_result_keys=", sorted(list(res[0].keys())))
PY

echo
echo "== basic evidence pointer checks =="
python3 - <<PY
import json
d=json.load(open("$TMP"))
res=d.get("results") or []
assert res, "no results"
for r in res:
    ev=r.get("evidence") or []
    for p in ev:
        for k in ["doc_id","chunk_id","char_start","char_end","quote_hash","snippet"]:
            assert k in p, f"missing {k} in evidence pointer"
print("evidence pointer fields ok")
PY

rm -f "$TMP"
echo
echo "assessments smoke ok"
