"""roles tables

Revision ID: 0a73c1d8b63a
Revises: 2a13d08b5c33
Create Date: 2026-01-16 07:44:18.478922

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a73c1d8b63a'
down_revision: Union[str, Sequence[str], None] = '2a13d08b5c33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS roles (
      role_id TEXT PRIMARY KEY,
      role_title TEXT NOT NULL,
      description TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS role_skill_requirements (
      req_id UUID PRIMARY KEY,
      role_id TEXT NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
      skill_id TEXT NOT NULL,
      required BOOLEAN NOT NULL DEFAULT true,
      target_level INTEGER NOT NULL DEFAULT 0,
      weight NUMERIC NOT NULL DEFAULT 1.0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_role_req_role ON role_skill_requirements(role_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_role_req_skill ON role_skill_requirements(skill_id);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_role_skill ON role_skill_requirements(role_id, skill_id);")


