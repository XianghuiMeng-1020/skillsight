"""skill aliases

Revision ID: 2a13d08b5c33
Revises: 2ba356720a89
"""

from typing import Sequence, Union
from alembic import op

revision: str = "2a13d08b5c33"
down_revision: Union[str, None] = "2ba356720a89"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS skill_aliases (
      alias_id UUID PRIMARY KEY,
      skill_id TEXT NOT NULL,
      alias TEXT NOT NULL,
      source TEXT NOT NULL DEFAULT 'manual',
      confidence NUMERIC NOT NULL DEFAULT 1.0,
      status TEXT NOT NULL DEFAULT 'active',  -- active/needs_review/deprecated
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_skill_aliases_alias ON skill_aliases(alias);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_skill_aliases_skill ON skill_aliases(skill_id);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_skill_aliases_pair ON skill_aliases(skill_id, alias);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS skill_aliases;")
