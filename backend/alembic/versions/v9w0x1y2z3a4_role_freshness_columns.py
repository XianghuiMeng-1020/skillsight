"""Add freshness columns to roles (first_seen_at, last_seen_at)

Revision ID: v9w0x1y2z3a4
Revises: u8v9w0x1y2z3
Create Date: 2026-04-17

Adds two timestamp columns and an index supporting the dashboard's
"role freshness" badge:

* ``first_seen_at`` — when this role was first observed in the market
                     (back-filled from ``created_at`` for existing rows).
* ``last_seen_at``  — most recent time the role was re-observed by any
                     ingestion path.  Refresh scripts bump this on
                     every run.

Both default to ``now()`` so newly inserted rows are correct
out-of-the-box; existing rows are back-filled to ``created_at`` so the
freshness label is meaningful from day one.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "v9w0x1y2z3a4"
down_revision: Union[str, Sequence[str], None] = "u8v9w0x1y2z3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE roles
        ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ DEFAULT now();
        """
    )
    op.execute(
        """
        ALTER TABLE roles
        ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ DEFAULT now();
        """
    )
    # Back-fill existing rows from created_at so the badge shows
    # something meaningful immediately.
    op.execute(
        """
        UPDATE roles
        SET first_seen_at = COALESCE(first_seen_at, created_at, now()),
            last_seen_at  = COALESCE(last_seen_at,  created_at, now())
        WHERE first_seen_at IS NULL OR last_seen_at IS NULL;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_roles_last_seen_at "
        "ON roles(last_seen_at DESC NULLS LAST);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_roles_last_seen_at;")
    op.execute("ALTER TABLE roles DROP COLUMN IF EXISTS last_seen_at;")
    op.execute("ALTER TABLE roles DROP COLUMN IF EXISTS first_seen_at;")
