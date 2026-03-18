#!/usr/bin/env python3
"""Apply scripts/fix_railway_missing_tables.sql using DATABASE_URL.

Usage (from repo root, with Railway backend service linked):
  railway run python3 scripts/apply_fix_railway_schema.py

Or:  export DATABASE_URL=... && python3 scripts/apply_fix_railway_schema.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _statements(sql: str) -> list[str]:
    """Split SQL into executable statements (handles multiline CREATE TABLE)."""
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    for line in sql.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        buf.append(line)
        depth += s.count("(") - s.count(")")
        if s.endswith(";") and depth <= 0:
            stmt = "\n".join(buf).strip()
            if stmt.endswith(";"):
                stmt = stmt[:-1].strip()
            if stmt:
                out.append(stmt)
            buf = []
            depth = 0
    return out


def main() -> int:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 1
    url = re.sub(r"^postgresql\+psycopg2://", "postgresql://", url)
    try:
        import psycopg
    except ImportError:
        print("Install: pip install 'psycopg[binary]'", file=sys.stderr)
        return 1

    sql_path = ROOT / "scripts" / "fix_railway_missing_tables.sql"
    stmts = _statements(sql_path.read_text(encoding="utf-8"))
    with psycopg.connect(url, autocommit=True) as conn:
        with conn.cursor() as cur:
            for stmt in stmts:
                try:
                    cur.execute(stmt)
                except Exception as e:
                    print(f"Error:\n{stmt[:300]}...\n{e}", file=sys.stderr)
                    return 1
    print(f"OK: executed {len(stmts)} statements from fix_railway_missing_tables.sql")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
