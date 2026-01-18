#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_PY="backend/alembic/env.py"
INI="backend/alembic.ini"

echo "[1/3] Backup env.py + alembic.ini"
cp "$ENV_PY" "$ENV_PY.bak.$(date +%Y%m%d%H%M%S)" || true
cp "$INI" "$INI.bak.$(date +%Y%m%d%H%M%S)" || true

echo "[2/3] Patch alembic.ini to use env DATABASE_URL as primary"
python - <<'PY'
from pathlib import Path
import re

p = Path("backend/alembic.ini")
s = p.read_text(encoding="utf-8")

# ensure [alembic] sqlalchemy.url exists; set a harmless fallback
if re.search(r'^\s*sqlalchemy\.url\s*=', s, flags=re.M) is None:
    s = s.replace("[alembic]", "[alembic]\nsqlalchemy.url = postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight\n", 1)
else:
    s = re.sub(r'^\s*sqlalchemy\.url\s*=.*$',
               "sqlalchemy.url = postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight",
               s, flags=re.M)

p.write_text(s, encoding="utf-8")
print("✅ Patched backend/alembic.ini sqlalchemy.url fallback")
PY

echo "[3/3] Rewrite env.py to a standard, Alembic-compatible template (uses DATABASE_URL if set)"
cat > "$ENV_PY" <<'PY'
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Alembic Config object (only exists when run via alembic CLI)
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---- Provide MetaData for autogenerate ----
target_metadata = None
_last_err = None

for mod_path in (
    # Try common layouts; we’ll lock this once we find your Base.
    "backend.app.db.base",
    "backend.app.database",
    "backend.app.db",
    "backend.app.models.base",
    "backend.app.models",
):
    try:
        mod = __import__(mod_path, fromlist=["Base"])
        Base = getattr(mod, "Base", None)
        if Base is not None and getattr(Base, "metadata", None) is not None:
            target_metadata = Base.metadata
            _last_err = None
            break
    except Exception as e:
        _last_err = e

if target_metadata is None:
    # Autogenerate will fail until Base.metadata is resolved, but upgrades can still run.
    print("[alembic] WARNING: target_metadata is None. Autogenerate will not work until Base.metadata import is fixed.")
    if _last_err is not None:
        print("[alembic] Last import error:", _last_err)

def get_url() -> str:
    # Prefer DATABASE_URL exported in shell
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url
    return config.get_main_option("sqlalchemy.url")

def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
PY

echo "✅ Alembic patch applied."
echo ""
echo "Next:"
echo "  export DATABASE_URL='postgresql+psycopg2://skillsight:skillsight@localhost:55432/skillsight'"
echo "  alembic -c backend/alembic.ini current"
echo "  alembic -c backend/alembic.ini upgrade head"
