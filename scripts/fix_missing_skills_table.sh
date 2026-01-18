#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

HOST="${PGHOST:-localhost}"
PORT="${PGPORT:-55432}"
USER="${PGUSER:-skillsight}"
DB="${PGDATABASE:-skillsight}"
PASS="${PGPASSWORD:-skillsight}"

SEED_JSON="backend/data/seeds/skills.json"
if [ ! -f "$SEED_JSON" ]; then
  echo "❌ Seed file not found: $SEED_JSON"
  exit 1
fi

echo "== 1) Ensure public.skills exists =="
PGPASSWORD="$PASS" psql -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" <<'SQL'
CREATE TABLE IF NOT EXISTS public.skills (
  skill_id            text PRIMARY KEY,
  canonical_name      text,
  definition          text,
  evidence_rules      jsonb,
  level_rubric_json   jsonb,
  version             text,
  source              text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_skills_canonical_name ON public.skills (canonical_name);
SQL

echo "== 2) Upsert from backend/data/seeds/skills.json =="
python3 - <<'PY'
import json, pathlib, datetime

seed_path = pathlib.Path("backend/data/seeds/skills.json")
data = json.loads(seed_path.read_text(encoding="utf-8"))

def pick(obj, *keys):
    for k in keys:
        if k in obj and obj[k] is not None:
            return obj[k]
    return None

rows = []
for x in data:
    sid = pick(x, "skill_id", "id")
    if not sid:
        # skip invalid
        continue
    row = {
        "skill_id": sid,
        "canonical_name": pick(x, "canonical_name", "name", "title"),
        "definition": pick(x, "definition", "desc", "description"),
        "evidence_rules": pick(x, "evidence_rules", "evidence", "evidencePointers", "evidence_pointer_rules"),
        "level_rubric_json": pick(x, "level_rubric_json", "level_rubric", "rubric"),
        "version": pick(x, "version"),
        "source": pick(x, "source"),
    }
    rows.append(row)

sql_lines = []
sql_lines.append("BEGIN;")
sql_lines.append("SET search_path TO public;")
sql_lines.append("""
INSERT INTO skills
(skill_id, canonical_name, definition, evidence_rules, level_rubric_json, version, source)
VALUES
""".strip())

vals = []
for r in rows:
    # json.dumps makes valid JSON even for strings (becomes JSON string)
    ev = json.dumps(r["evidence_rules"], ensure_ascii=False) if r["evidence_rules"] is not None else None
    rb = json.dumps(r["level_rubric_json"], ensure_ascii=False) if r["level_rubric_json"] is not None else None

    def q(s):
        if s is None:
            return "NULL"
        return "'" + str(s).replace("\\", "\\\\").replace("'", "''") + "'"

    v = "(" + ", ".join([
        q(r["skill_id"]),
        q(r["canonical_name"]),
        q(r["definition"]),
        (q(ev) + "::jsonb") if ev is not None else "NULL",
        (q(rb) + "::jsonb") if rb is not None else "NULL",
        q(r["version"]),
        q(r["source"]),
    ]) + ")"
    vals.append(v)

if not vals:
    raise SystemExit("No valid rows found in skills.json (missing skill_id).")

sql_lines.append(",\n".join(vals))
sql_lines.append("""
ON CONFLICT (skill_id) DO UPDATE SET
  canonical_name = EXCLUDED.canonical_name,
  definition = EXCLUDED.definition,
  evidence_rules = EXCLUDED.evidence_rules,
  level_rubric_json = EXCLUDED.level_rubric_json,
  version = EXCLUDED.version,
  source = EXCLUDED.source,
  updated_at = now();
""".strip())
sql_lines.append("COMMIT;")

out = pathlib.Path("logs") / f"upsert_skills_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.sql"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(sql_lines) + "\n", encoding="utf-8")
print(str(out))
PY

SQLFILE=$(ls -1t logs/upsert_skills_*.sql | head -n 1)
echo "== Running $SQLFILE =="
PGPASSWORD="$PASS" psql -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -f "$SQLFILE"

echo "== 3) Quick check =="
PGPASSWORD="$PASS" psql -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -c "SELECT COUNT(*) AS skills_count FROM public.skills;"
PGPASSWORD="$PASS" psql -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -c "SELECT skill_id, canonical_name FROM public.skills ORDER BY 2 NULLS LAST LIMIT 5;"

echo "✅ public.skills created + seeds upserted."
