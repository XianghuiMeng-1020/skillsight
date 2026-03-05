#!/usr/bin/env bash
# E2E Golden Path Check - fail-fast with clear step numbers
# Usage: ./scripts/e2e_golden_path.sh [API_BASE] [DB_PORT]
set -euo pipefail

API_BASE="${1:-http://127.0.0.1:8001}"
DB_PORT="${2:-55432}"
FAILED_AT=""

fail() {
  echo ""
  echo "=========================================="
  echo "FAILED AT STEP $1"
  echo "=========================================="
  echo "$2"
  exit 1
}

echo "=== E2E Golden Path Check ==="
echo "API_BASE=$API_BASE DB_PORT=$DB_PORT"
echo ""

# Step 1: Health
echo "[STEP 1] GET /health"
if ! curl -fsS "$API_BASE/health" >/dev/null; then
  fail 1 "Health check failed. Is the backend running at $API_BASE?"
fi
echo "  OK"

# Step 2: Dev login
echo "[STEP 2] POST /auth/dev_login"
LOGIN_RESP=$(curl -fsS -X POST "$API_BASE/auth/dev_login" \
  -H "Content-Type: application/json" \
  -d '{"subject_id":"e2e_test_user","role":"student","ttl_s":3600}' 2>/dev/null) || fail 2 "Dev login failed"
TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
if [ -z "$TOKEN" ]; then
  fail 2 "No token in login response: $LOGIN_RESP"
fi
echo "  OK (token obtained)"

# Step 3: Upload plain text document
echo "[STEP 3] POST /documents/import (plain text)"
TEST_FILE=$(mktemp)
echo "This document demonstrates Python programming skills. I wrote a script to process CSV data and generate reports. The code uses pandas for data manipulation and includes unit tests." > "$TEST_FILE"
UPLOAD_RESP=$(curl -fsS -X POST "$API_BASE/documents/import" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$TEST_FILE;filename=evidence.txt" 2>/dev/null) || fail 3 "Document import failed"
DOC_ID=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('doc_id',''))" 2>/dev/null)
rm -f "$TEST_FILE"
if [ -z "$DOC_ID" ]; then
  fail 3 "No doc_id in upload response: $UPLOAD_RESP"
fi
echo "  OK (doc_id=$DOC_ID)"

# Step 4: Embed chunks (sync, no Redis)
echo "[STEP 4] POST /chunks/embed/$DOC_ID"
EMBED_RESP=$(curl -fsS -X POST "$API_BASE/chunks/embed/$DOC_ID" \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null) || fail 4 "Chunk embed failed"
EMBEDDED=$(echo "$EMBED_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('chunks_embedded',0))" 2>/dev/null)
if [ "${EMBEDDED:-0}" -eq 0 ]; then
  fail 4 "No chunks embedded. Response: $EMBED_RESP"
fi
echo "  OK (chunks_embedded=$EMBEDDED)"

# Step 5: Verify chunks in DB
echo "[STEP 5] Verify chunks in DB"
CHUNK_COUNT=$(PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A -c "SELECT COUNT(*) FROM chunks WHERE doc_id = '$DOC_ID';" 2>/dev/null) || fail 5 "DB query failed (is psql available? is DB on port $DB_PORT?)"
CHUNK_COUNT=$(echo "$CHUNK_COUNT" | tr -d ' ')
if [ "${CHUNK_COUNT:-0}" -eq 0 ]; then
  fail 5 "No chunks in DB for doc_id=$DOC_ID"
fi
echo "  OK (chunks=$CHUNK_COUNT)"

# Step 6: Verify Qdrant collection and points
echo "[STEP 6] Verify Qdrant collection"
# Use Qdrant REST API
QD_COUNT=$(curl -fsS "http://127.0.0.1:6333/collections/chunks_v1" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result',{}).get('points_count',0))" 2>/dev/null) || fail 6 "Qdrant collection check failed"
if [ -z "$QD_COUNT" ] || [ "${QD_COUNT:-0}" -eq 0 ]; then
  fail 6 "Qdrant collection chunks_v1 has 0 points or does not exist"
fi
echo "  OK (points_count=$QD_COUNT)"

# Step 7: Search evidence_vector
echo "[STEP 7] POST /search/evidence_vector"
SEARCH_RESP=$(curl -fsS -X POST "$API_BASE/search/evidence_vector" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"query_text\":\"Python programming data processing\",\"doc_id\":\"$DOC_ID\",\"k\":5}" 2>/dev/null) || fail 7 "Evidence vector search failed"
ITEMS=$(echo "$SEARCH_RESP" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('items',[])))" 2>/dev/null)
if [ "${ITEMS:-0}" -eq 0 ]; then
  fail 7 "Search returned 0 items. Response: $SEARCH_RESP"
fi
echo "  OK (items=$ITEMS)"

# Step 7.5: Seed a skill if none exist (required for STEP 8)
SKILL_ID=$(PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A -c "SELECT skill_id FROM skills LIMIT 1;" 2>/dev/null | tr -d ' ')
if [ -z "$SKILL_ID" ]; then
  echo "[STEP 7.5] Seeding test skill via /skills/import"
  SEED_RESP=$(curl -fsS -X POST "$API_BASE/skills/import" \
    -H "Content-Type: application/json" \
    -d '[{
      "skill_id": "HKU.SKILL.PYTHON.v1",
      "canonical_name": "Python Programming",
      "definition": "Ability to write Python scripts, process data, and build automation tools.",
      "evidence_rules": "Look for Python code, scripts, data processing, pandas, unit tests.",
      "aliases": ["Python", "python programming", "scripting"],
      "level_rubric": {
        "levels": {
          "0": {"label": "novice", "criteria": [{"id": "p0a", "text": "No evidence of Python usage"}]},
          "1": {"label": "developing", "criteria": [{"id": "p1a", "text": "Basic Python scripts"}]},
          "2": {"label": "proficient", "criteria": [{"id": "p2a", "text": "Uses libraries like pandas"}]},
          "3": {"label": "advanced", "criteria": [{"id": "p3a", "text": "Production-quality Python with tests"}]}
        }
      },
      "version": "v1",
      "source": "e2e_seed"
    }]' 2>/dev/null) || fail 8 "Failed to seed skill"
  SKILL_ID="HKU.SKILL.PYTHON.v1"
  echo "  OK (seeded skill_id=$SKILL_ID)"
else
  echo "[STEP 7.5] Using existing skill_id=$SKILL_ID"
fi

# Step 8: AI demonstration (needs skill_id)
echo "[STEP 8] POST /ai/demonstration"
DEMO_RESP=$(curl -fsS -X POST "$API_BASE/ai/demonstration" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"skill_id\":\"$SKILL_ID\",\"doc_id\":\"$DOC_ID\",\"k\":5}" 2>/dev/null) || fail 8 "AI demonstration failed"
LABEL=$(echo "$DEMO_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('label',''))" 2>/dev/null)
EIDS=$(echo "$DEMO_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('evidence_chunk_ids',[]))" 2>/dev/null)
if [ -z "$LABEL" ]; then
  fail 8 "No label in demonstration response: $DEMO_RESP"
fi
echo "  OK (label=$LABEL, evidence_chunk_ids=$EIDS)"

# Step 9: Role readiness (needs role_id - seed if missing)
ROLE_ID=$(PGPASSWORD=skillsight psql -h 127.0.0.1 -p "$DB_PORT" -U skillsight -d skillsight -t -A -c "SELECT role_id FROM roles LIMIT 1;" 2>/dev/null | tr -d ' ')
if [ -z "$ROLE_ID" ]; then
  echo "  Seeding test role via /roles/import"
  curl -fsS -X POST "$API_BASE/roles/import" \
    -H "Content-Type: application/json" \
    -d "[{
      \"role_id\": \"HKU.ROLE.DATA_ANALYST.v1\",
      \"role_title\": \"Data Analyst\",
      \"description\": \"Analyses data using Python, SQL and visualisation tools.\",
      \"skills_required\": [{\"skill_id\": \"$SKILL_ID\", \"min_level\": 2, \"weight\": 1.0}]
    }]" 2>/dev/null || fail 9 "Failed to seed role"
  ROLE_ID="HKU.ROLE.DATA_ANALYST.v1"
  echo "  OK (seeded role_id=$ROLE_ID)"
fi
echo "[STEP 9] POST /assess/role_readiness (role_id=$ROLE_ID)"
READINESS_RESP=$(curl -fsS -X POST "$API_BASE/assess/role_readiness" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"doc_id\":\"$DOC_ID\",\"role_id\":\"$ROLE_ID\"}" 2>/dev/null) || fail 9 "Role readiness failed"
SCORE=$(echo "$READINESS_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('score',-1))" 2>/dev/null)
if [ -z "$SCORE" ] || [ "$SCORE" = "-1" ]; then
  fail 9 "No score in readiness response: $READINESS_RESP"
fi
echo "  OK (score=$SCORE)"

# Step 10: Actions recommend
echo "[STEP 10] POST /actions/recommend"
ACTIONS_RESP=$(curl -fsS -X POST "$API_BASE/actions/recommend" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"doc_id\":\"$DOC_ID\",\"role_id\":\"$ROLE_ID\"}" 2>/dev/null) || fail 10 "Actions recommend failed"
ACTIONS_COUNT=$(echo "$ACTIONS_RESP" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('actions',[])))" 2>/dev/null)
echo "  OK (actions_count=$ACTIONS_COUNT)"

echo ""
echo "=========================================="
echo "ALL 10 STEPS PASSED"
echo "=========================================="
