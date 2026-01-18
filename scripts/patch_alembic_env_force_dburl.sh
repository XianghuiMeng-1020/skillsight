#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_PY="$ROOT/backend/alembic/env.py"
INI="$ROOT/backend/alembic.ini"

[ -f "$ENV_PY" ] || { echo "❌ $ENV_PY not found"; exit 1; }
[ -f "$INI" ] || { echo "❌ $INI not found"; exit 1; }

TS="$(date +%Y%m%d%H%M%S)"
cp "$ENV_PY" "$ENV_PY.bak.$TS"
cp "$INI" "$INI.bak.$TS"

cat > "$ENV_PY" <<'PY'
from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# this is the Alembic Config object, which provides access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- IMPORTANT: force DATABASE_URL if provided ---
db_url = os.getenv("DATABASE_URL")
if db_url:
    # ensure alembic uses env var and not stale ini config
    config.set_main_option("sqlalchemy.url", db_url)

# If your models live elsewhere, import Base and metadata here.
# We try common paths but stay safe if not present.
target_metadata = None
try:
    from backend.app.db import Base  # type: ignore
    target_metadata = Base.metadata
except Exception:
    try:
        from backend.app.models.base import Base  # type: ignore
        target_metadata = Base.metadata
    except Exception:
        target_metadata = None

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
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
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
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

echo "✅ Patched $ENV_PY (force DATABASE_URL). Backup: $ENV_PY.bak.$TS"
echo "✅ Patched $INI backup: $INI.bak.$TS"

# Print effective URL (masked password)
python - <<'PY'
import os
u=os.getenv("DATABASE_URL","")
if not u:
    print("⚠️ DATABASE_URL is not set in this shell.")
else:
    import re
    masked=re.sub(r'//([^:/]+):([^@]+)@', r'//\\1:****@', u)
    print("Using DATABASE_URL =", masked)
PY
