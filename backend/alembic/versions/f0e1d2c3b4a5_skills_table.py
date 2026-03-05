"""skills table

Revision ID: f0e1d2c3b4a5
Revises: cf8499c65090
Create Date: 2026-02-21

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f0e1d2c3b4a5"
down_revision: Union[str, None] = "cf8499c65090"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS skills (
      skill_id TEXT PRIMARY KEY,
      canonical_name TEXT NOT NULL,
      definition TEXT NOT NULL DEFAULT '',
      evidence_rules TEXT NOT NULL DEFAULT '',
      level_rubric_json TEXT NOT NULL DEFAULT '{}',
      version TEXT NOT NULL DEFAULT 'v1',
      source TEXT NOT NULL DEFAULT 'manual',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_skills_canonical ON skills(canonical_name);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS skills;")
