#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8001}"
DB_URL="${DB_URL:-postgresql://skillsight:skillsight@localhost:55432/skillsight}"

echo "== routes check =="
curl -fsS "${API_BASE}/__routes" > /tmp/routes.json
python3 -c "import json; d=json.load(open('/tmp/routes.json')); paths=[r['path'] for r in d];
need=['/skills','/skills/import','/documents/import','/assessments/run','/proficiency'];
missing=[x for x in need if x not in paths];
print('missing=',missing);
assert not missing"

echo
echo "== skills/import =="
curl -fsS -X POST "${API_BASE}/skills/import" -H "Content-Type: application/json" --data-binary @/tmp/skills_backfill.json \
 | python3 -c "import json,sys; print(json.load(sys.stdin))"

echo
echo "== import doc =="
cat > /tmp/doc_hit_full.txt <<'TXT'
This document describes a Python workflow for building an API service.
We used FastAPI and Uvicorn with SQLAlchemy and a Postgres database.
We ran python scripts for ingestion, verification, and hashing (sha256).
We discussed consent and privacy for handling personal data (PII) and de-identification.
We also followed citation rules and avoided plagiarism to maintain academic honesty.
TXT

DOC_ID="$(curl -fsS -F "file=@/tmp/doc_hit_full.txt" "${API_BASE}/documents/import?chunk_size=800&overlap=100" \
 | python3 -c "import json,sys; print(json.load(sys.stdin)['doc_id'])")"
echo "DOC_ID=${DOC_ID}"

echo
echo "== run assessments =="
curl -fsS -X POST "${API_BASE}/assessments/run?doc_id=${DOC_ID}" > /tmp/assess_out.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/assess_out.json"))
res=d.get("results") or []
assert res, "no results"
for r in res:
    ev=r.get("evidence") or []
    for p in ev:
        for k in ["doc_id","chunk_id","char_start","char_end","quote_hash","snippet"]:
            assert k in p, f"missing {k}"
print("✅ evidence pointer fields ok")
PY

echo
echo "== proficiency =="
curl -fsS "${API_BASE}/proficiency?doc_id=${DOC_ID}&latest_per_skill=true&limit=50" > /tmp/prof_out.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/prof_out.json"))
items=d.get("items") or []
assert items, "no proficiency items"
for it in items:
    be=it.get("best_evidence") or {}
    assert "chunk_id" in be, "best_evidence missing chunk_id"
print("✅ proficiency best_evidence ok")
PY

echo
echo "== DB audit =="
psql "$DB_URL" -c "SELECT COUNT(*) AS n FROM skill_assessments WHERE doc_id='${DOC_ID}';"
psql "$DB_URL" -c "SELECT COUNT(*) AS n FROM skill_proficiency WHERE doc_id='${DOC_ID}';"

echo "✅ e2e smoke full ok"
