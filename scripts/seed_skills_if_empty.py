#!/usr/bin/env python3
"""If skills table is empty, seed from backend/data/skills.json (Railway-friendly).

  railway run python3 scripts/seed_skills_if_empty.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("DATABASE_URL required", file=sys.stderr)
        return 1
    url = re.sub(r"^postgresql\+psycopg2://", "postgresql://", url)
    import psycopg

    skills_path = ROOT / "backend" / "data" / "skills.json"
    if not skills_path.exists():
        print(f"Missing {skills_path}", file=sys.stderr)
        return 1
    skills = json.loads(skills_path.read_text(encoding="utf-8"))

    now = datetime.now(timezone.utc)
    with psycopg.connect(url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM skills")
            if (cur.fetchone()[0] or 0) > 0:
                print("skills table already populated, skip")
                return 0
            for s in skills:
                sid = s.get("skill_id") or str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO skills (skill_id, canonical_name, definition,
                        evidence_rules, level_rubric_json, version, source, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (skill_id) DO NOTHING
                    """,
                    (
                        sid,
                        s.get("canonical_name", ""),
                        s.get("definition", ""),
                        s.get("evidence_rules", ""),
                        json.dumps(s.get("level_rubric", {}), ensure_ascii=False),
                        s.get("version", "v1"),
                        s.get("source", "seed"),
                        now,
                    ),
                )
                for a in s.get("aliases") or []:
                    if not str(a).strip():
                        continue
                    try:
                        cur.execute(
                            """
                            INSERT INTO skill_aliases (alias_id, skill_id, alias, source, confidence, status, created_at)
                            VALUES (%s, %s, %s, 'seed', 1.0, 'active', %s)
                            ON CONFLICT (skill_id, alias) DO NOTHING
                            """,
                            (str(uuid.uuid4()), sid, str(a).strip(), now),
                        )
                    except Exception as ex:
                        print(f"alias warn {sid}: {ex}", file=sys.stderr)
            cur.execute("SELECT COUNT(*) FROM skills")
            print(f"OK: skills count = {cur.fetchone()[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
