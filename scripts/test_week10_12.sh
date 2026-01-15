#!/usr/bin/env bash
set -euo pipefail

API="${API_BASE:-http://localhost:8000}"
SKILL_ID="${SKILL_ID:-HKU.SKILL.ACADEMIC_INTEGRITY.v1}"

H_STAFF=(-H "X-Subject-Id: staff_demo" -H "X-Role: staff")

echo "== Health =="
curl -s "$API/health"
echo

echo "== Week10: reindex embeddings =="

TMP_BODY=$(mktemp)
STATUS=$(curl -sS -o "$TMP_BODY" -w "%{http_code}" -X POST "$API/embeddings/reindex" "${H_STAFF[@]}")
echo "HTTP $STATUS"
cat "$TMP_BODY"

if [ "$STATUS" != "200" ]; then
  echo "ERROR: reindex returned HTTP $STATUS"
  exit 1
fi

python3 -c 'import json,sys; o=json.load(open(sys.argv[1])); print(o); assert o.get("ok") is True; assert int(o.get("count",0))>=1' "$TMP_BODY"

rm -f "$TMP_BODY"
echo

echo "== Week10: vector search (skill_id) =="

TMP_SEARCH=$(mktemp)
STATUS=$(curl -sS -o "$TMP_SEARCH" -w "%{http_code}" -X POST "$API/search/evidence_vector" "${H_STAFF[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"skill_id\":\"$SKILL_ID\",\"k\":5}")

echo "HTTP $STATUS"
cat "$TMP_SEARCH"
echo

if [ "$STATUS" != "200" ]; then
  echo "ERROR: vector search returned HTTP $STATUS"
  rm -f "$TMP_SEARCH"
  exit 1
fi

python3 -c 'import json,sys; o=json.load(open(sys.argv[1])); items=o.get("items") or []; assert len(items)>0, "vector search returned no items"; 
[(_ for _ in ()).throw(AssertionError("missing fields")) if (not it.get("chunk_id") or not it.get("doc_id") or it.get("snippet") is None) else None for it in items];
print("OK: items=", len(items))' "$TMP_SEARCH"

DOC_ID=$(python3 -c 'import json,sys; o=json.load(open(sys.argv[1])); print(o["items"][0]["doc_id"])' "$TMP_SEARCH")
echo "DOC_ID(sample)=$DOC_ID"

rm -f "$TMP_SEARCH"
echo
echo "== Week11: ai/demonstration positive =="

TMP_POS=$(mktemp)
STATUS=$(curl -sS -o "$TMP_POS" -w "%{http_code}" -X POST "$API/ai/demonstration" "${H_STAFF[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"skill_id\":\"$SKILL_ID\",\"k\":5,\"min_score\":0.2}")

echo "HTTP $STATUS"
cat "$TMP_POS"
echo

if [ "$STATUS" != "200" ]; then
  echo "ERROR: ai/demonstration positive returned HTTP $STATUS"
  rm -f "$TMP_POS"
  exit 1
fi

python3 -c 'import json,sys; o=json.load(open(sys.argv[1])); 
assert o["label"] in ["demonstrated","mentioned","not_enough_information"];
if o["label"] in ["demonstrated","mentioned"]:
  assert len(o["evidence_chunk_ids"])>=1;
else:
  assert o["evidence_chunk_ids"]==[];
  assert o["refusal_reason"];
print("OK:", o["label"], "evidence_ids=", len(o["evidence_chunk_ids"]))' "$TMP_POS"

rm -f "$TMP_POS"
echo
echo "== Week11: ai/demonstration refusal =="

TMP_NEG=$(mktemp)
STATUS=$(curl -sS -o "$TMP_NEG" -w "%{http_code}" -X POST "$API/ai/demonstration" "${H_STAFF[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"skill_id\":\"$SKILL_ID\",\"k\":5,\"min_score\":0.95}")

echo "HTTP $STATUS"
cat "$TMP_NEG"
echo

if [ "$STATUS" != "200" ]; then
  echo "ERROR: ai/demonstration refusal returned HTTP $STATUS"
  rm -f "$TMP_NEG"
  exit 1
fi

python3 -c 'import json,sys; o=json.load(open(sys.argv[1])); 
assert o["label"]=="not_enough_information";
assert o["evidence_chunk_ids"]==[];
assert o["refusal_reason"];
print("OK: refused with reason:", o["refusal_reason"])' "$TMP_NEG"

rm -f "$TMP_NEG"
echo
echo "== Week12: ai/proficiency consistency x3 =="

levels=""
criteria=""

for i in 1 2 3; do
  TMP_P=$(mktemp)
  STATUS=$(curl -sS -o "$TMP_P" -w "%{http_code}" -X POST "$API/ai/proficiency" "${H_STAFF[@]}" \
    -H "Content-Type: application/json" \
    -d "{\"skill_id\":\"$SKILL_ID\",\"k\":5,\"min_score\":0.2}")
  echo "run $i HTTP $STATUS"
  cat "$TMP_P"
  echo
  if [ "$STATUS" != "200" ]; then
    echo "ERROR: ai/proficiency returned HTTP $STATUS"
    rm -f "$TMP_P"
    exit 1
  fi

  LV=$(python3 -c 'import json,sys; o=json.load(open(sys.argv[1])); print(o["level"])' "$TMP_P")
  CR=$(python3 -c 'import json,sys; o=json.load(open(sys.argv[1])); print(",".join(o["matched_criteria"]))' "$TMP_P")

  if [ -z "$levels" ]; then
    levels="$LV"
    criteria="$CR"
  else
    if [ "$LV" != "$levels" ] || [ "$CR" != "$criteria" ]; then
      echo "ERROR: inconsistency detected. baseline level=$levels criteria=$criteria, got level=$LV criteria=$CR"
      rm -f "$TMP_P"
      exit 1
    fi
  fi
  rm -f "$TMP_P"
done

echo "OK: stable level=$levels criteria=$criteria"
echo
echo "ALL TESTS PASSED ✅"
