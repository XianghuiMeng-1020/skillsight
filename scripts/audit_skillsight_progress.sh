#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8001}"
DB_URL="${DB_URL:-postgresql://skillsight:skillsight@localhost:55432/skillsight}"

TS="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="reports"
OUT="${OUT_DIR}/skillsight_audit_${TS}.md"
mkdir -p "$OUT_DIR"

say() { echo -e "$*" | tee -a "$OUT" >/dev/null; }
hr() { say "\n---\n"; }

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "❌ missing command: $1"; exit 1; }; }
need_cmd curl
need_cmd python3
need_cmd psql

say "# SkillSight Progress Audit"
say "- time: ${TS}"
say "- API: ${API_BASE}"
say "- DB: ${DB_URL}"
hr

say "## 0) Backend health"
if curl -fsS "${API_BASE}/health" >/dev/null 2>&1; then
  say "✅ /health OK"
else
  say "❌ /health FAILED. Is uvicorn running on :8001?"
  exit 1
fi

hr
say "## 1) Route coverage (OpenAPI)"
ROUTES_JSON="$(mktemp)"
if curl -fsS "${API_BASE}/openapi.json" -o "$ROUTES_JSON" >/dev/null 2>&1; then
  python3 - "$ROUTES_JSON" "$OUT" <<'PY'
import json,sys
p=sys.argv[1]; out=sys.argv[2]
o=json.load(open(p,"r"))
paths=sorted(o.get("paths",{}).keys())

targets = {
  "skills": ["/skills", "/skills/import"],
  "roles": ["/roles", "/roles/{role_id}"],
  "documents": ["/documents"],
  "chunks": ["/chunks"],
  "consents": ["/consents", "/consent/grant", "/consent/revoke"],
  "jobs": ["/jobs"],
  "courses": ["/courses"],
}

def has_prefix(prefix: str) -> bool:
  return any(x.startswith(prefix) for x in paths)

def check_group(name, candidates):
  found=[]
  for c in candidates:
    if c in paths:
      found.append(c)
  if not found:
    for c in candidates:
      base=c.split("{")[0].rstrip("/")
      if base and has_prefix(base):
        found.append(f"{c} (prefix match: {base})")
  return found

with open(out,"a") as f:
  for k,v in targets.items():
    found=check_group(k,v)
    if found:
      f.write(f"- ✅ {k}: " + ", ".join(found) + "\n")
    else:
      f.write(f"- ❌ {k}: not found in openapi paths\n")

  f.write("\n### All API paths (debug)\n")
  for pth in paths:
    f.write(f"- {pth}\n")
PY
  say "✅ Wrote route audit section"
else
  say "⚠️ Could not fetch /openapi.json"
fi

hr
say "## 2) Database tables + row counts"

say "### Tables (public)"
say '```'
psql "$DB_URL" -v ON_ERROR_STOP=1 -q -c "
SELECT table_name
FROM information_schema.tables
WHERE table_schema='public'
ORDER BY table_name;
" | sed 's/[[:space:]]*$//' | tee -a "$OUT" >/dev/null
say '```'

say "### Row counts (key tables)"
psql "$DB_URL" -v ON_ERROR_STOP=1 -q -c "
SELECT 'skills' as tbl, count(*) as n FROM skills
UNION ALL SELECT 'skill_aliases', count(*) FROM skill_aliases
UNION ALL SELECT 'roles', count(*) FROM roles
UNION ALL SELECT 'role_skill_requirements', count(*) FROM role_skill_requirements
UNION ALL SELECT 'courses', count(*) FROM courses
UNION ALL SELECT 'course_skill_map', count(*) FROM course_skill_map
UNION ALL SELECT 'documents', count(*) FROM documents
UNION ALL SELECT 'chunks', count(*) FROM chunks
UNION ALL SELECT 'consents', count(*) FROM consents
UNION ALL SELECT 'jobs', count(*) FROM jobs
UNION ALL SELECT 'skill_assessments', count(*) FROM skill_assessments
UNION ALL SELECT 'skill_proficiency', count(*) FROM skill_proficiency
ORDER BY tbl;
" | tee -a "$OUT" >/dev/null

hr
hr
hr
say "## 2.5) Foreign keys"
psql "$DB_URL" -Atc "
SELECT
  con.conname || ': ' ||
  src.relname || '.' || a.attname || ' -> ' ||
  ref.relname || '.' || af.attname || ' (validated=' || con.convalidated || ')'
FROM pg_constraint con
JOIN pg_class src ON src.oid = con.conrelid
JOIN pg_class ref ON ref.oid = con.confrelid
JOIN LATERAL unnest(con.conkey)  WITH ORDINALITY AS ck(attnum, ord)  ON TRUE
JOIN LATERAL unnest(con.confkey) WITH ORDINALITY AS fk(attnum, ord)  ON fk.ord = ck.ord
JOIN pg_attribute a  ON a.attrelid = src.oid AND a.attnum = ck.attnum
JOIN pg_attribute af ON af.attrelid = ref.oid AND af.attnum = fk.attnum
WHERE con.contype='f'
ORDER BY con.conname;
" | sed 's/^/ - /' | tee -a "$OUT" >/dev/null

say "## 3) Minimal functional tests (non-destructive)"

say "### 3.1 skills list/search"
curl -fsS "${API_BASE}/skills?q=HKU" | python3 -c "import json,sys; d=json.load(sys.stdin); print('✅ skills returned:', len(d))" | tee -a "$OUT" >/dev/null || say "❌ /skills query failed"

say "### 3.2 roles list"
curl -fsS "${API_BASE}/roles" | python3 -c "import json,sys; d=json.load(sys.stdin); print('✅ roles count:', d.get('count'))" | tee -a "$OUT" >/dev/null || say "❌ /roles failed"

say "### 3.3 documents list (GET /documents)"
TMP_BODY="$(mktemp)"
DOC_ID=""
HTTP_CODE="$(curl -sS -o "$TMP_BODY" -w "%{http_code}" "${API_BASE}/documents?limit=5" || true)"
if [ "$HTTP_CODE" = "200" ]; then
  python3 - "$TMP_BODY" <<'PYDOC' | tee -a "$OUT" >/dev/null
import json,sys
p=sys.argv[1]
d=json.load(open(p))
items = d.get("items") if isinstance(d, dict) else None
if items is None and isinstance(d, list):
    items = d
count = d.get("count") if isinstance(d, dict) else (len(items) if items is not None else None)
print("✅ documents count:", count)
doc_id = ""
if items and isinstance(items, list) and len(items)>0 and isinstance(items[0], dict):
    doc_id = items[0].get("doc_id") or items[0].get("id") or ""
print("DOC_ID="+(doc_id or ""))
PYDOC
  DOC_ID="$(python3 -c "import json; d=json.load(open('$TMP_BODY')); items=d.get('items') if isinstance(d,dict) else d; \
doc_id=(items[0].get('doc_id') or items[0].get('id') or '') if isinstance(items,list) and items and isinstance(items[0],dict) else ''; \
print(doc_id)")"
else
  say "❌ /documents failed (http=$HTTP_CODE)"
  say "body(head): $(head -c 300 "$TMP_BODY" | tr '\n' ' ')"
fi
rm -f "$TMP_BODY"

say "### 3.4 documents get one (GET /documents/{doc_id})"
if [ -n "${DOC_ID}" ]; then
  if curl -fsS "${API_BASE}/documents/${DOC_ID}" >/dev/null 2>&1; then
    say "✅ document fetch ok: ${DOC_ID}"
  else
    say "❌ /documents/{doc_id} failed: ${DOC_ID}"
  fi
else
  say "⚠️ skipped (no DOC_ID from /documents list)"
fi

say "### 3.5 chunks list (GET /chunks)"
TMP_BODY="$(mktemp)"
if curl -fsS "${API_BASE}/chunks?limit=5" -o "$TMP_BODY" >/dev/null 2>&1; then
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("✅ chunks count:", d.get("count"))' "$TMP_BODY" | tee -a "$OUT" >/dev/null
else
  say "❌ /chunks failed"
fi
rm -f "$TMP_BODY"

say "### 3.6 chunks by doc (GET /documents/{doc_id}/chunks)"
if [ -n "${DOC_ID}" ]; then
  TMP_BODY="$(mktemp)"
  if curl -fsS "${API_BASE}/documents/${DOC_ID}/chunks?limit=5" -o "$TMP_BODY" >/dev/null 2>&1; then
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("✅ doc chunks count:", d.get("count"))' "$TMP_BODY" | tee -a "$OUT" >/dev/null
  else
    say "❌ /documents/{doc_id}/chunks failed: ${DOC_ID}"
  fi
  rm -f "$TMP_BODY"
else
  say "⚠️ skipped (no DOC_ID)"
fi

say "### 3.7 consents list (GET /consents)"
TMP_BODY="$(mktemp)"
if curl -fsS "${API_BASE}/consents" -o "$TMP_BODY" >/dev/null 2>&1; then
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("✅ consents count:", d.get("count"))' "$TMP_BODY" | tee -a "$OUT" >/dev/null
else
  say "❌ /consents failed"
fi
rm -f "$TMP_BODY"

say "### 3.8 jobs list (GET /jobs)"
TMP_BODY="$(mktemp)"
if curl -fsS "${API_BASE}/jobs" -o "$TMP_BODY" >/dev/null 2>&1; then
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("✅ jobs count:", d.get("count"))' "$TMP_BODY" | tee -a "$OUT" >/dev/null
else
  say "❌ /jobs failed"
fi
rm -f "$TMP_BODY"

say "### 3.9 courses list (GET /courses and /course-skill-map)"
TMP_BODY="$(mktemp)"
if curl -fsS "${API_BASE}/courses" -o "$TMP_BODY" >/dev/null 2>&1; then
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("✅ courses count:", d.get("count"))' "$TMP_BODY" | tee -a "$OUT" >/dev/null
else
  say "❌ /courses failed"
fi
rm -f "$TMP_BODY"

TMP_BODY="$(mktemp)"
if curl -fsS "${API_BASE}/course-skill-map?limit=10" -o "$TMP_BODY" >/dev/null 2>&1; then
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("✅ course-skill-map count:", d.get("count"))' "$TMP_BODY" | tee -a "$OUT" >/dev/null
else
  say "❌ /course-skill-map failed"
fi
rm -f "$TMP_BODY"

hr
say "## Summary flags"
say "- If route exists but row count is 0, it likely means 'implemented but not exercised'."
say "- If table exists but route missing, it's 'migrated but API not wired'."
say "- If both missing, it's 'not implemented'."

say "\n✅ Report written to: ${OUT}"
echo "✅ Report written to: ${OUT}"
