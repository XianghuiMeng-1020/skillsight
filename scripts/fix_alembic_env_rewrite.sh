#!/usr/bin/env bash
set -euo pipefail

ENV_PY="backend/alembic/env.py"
if [[ ! -f "$ENV_PY" ]]; then
  echo "❌ Not found: $ENV_PY"
  exit 1
fi

cp "$ENV_PY" "${ENV_PY}.bak.$(date -u +%Y%m%d%H%M%S)"
echo "✅ Backed up $ENV_PY"

cat > "$ENV_PY" <<'PY'
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# --- Ensure repo root is importable so `backend.*` works ---
ROOT = Path(__file__).resolve().parents[2]  # /skillsight
sys.path.insert(0, str(ROOT))

# Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Import your SQLAlchemy Base + register models ---
from backend.app.db.base import Base  # noqa: E402
import backend.app.models  # noqa: F401,E402  (register tables)

target_metadata = Base.metadata

def get_url() -> str:
    # Prefer env var, fall back to alembic.ini sqlalchemy.url
    url = os.getenv("DATABASE_URL")
    if url:
        return url
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

echo "✅ Rewrote backend/alembic/env.py"
