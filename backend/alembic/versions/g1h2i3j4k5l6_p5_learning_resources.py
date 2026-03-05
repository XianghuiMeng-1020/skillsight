"""P5: learning_resources and resource_skill_map tables

Revision ID: g1h2i3j4k5l6
Revises: c2d3e4f5a6b7
Create Date: 2026-02-22

Decision 5: Resource library for action recommendations.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS learning_resources (
            resource_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title TEXT NOT NULL,
            resource_type TEXT NOT NULL DEFAULT 'course',
            location TEXT,
            url TEXT,
            description TEXT,
            gap_type TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_learning_resources_gap ON learning_resources(gap_type);")

    op.execute("""
        CREATE TABLE IF NOT EXISTS resource_skill_map (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            resource_id UUID NOT NULL REFERENCES learning_resources(resource_id) ON DELETE CASCADE,
            skill_id TEXT NOT NULL,
            gap_type TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_resource_skill_skill ON resource_skill_map(skill_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_resource_skill_gap ON resource_skill_map(gap_type);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS resource_skill_map;")
    op.execute("DROP TABLE IF EXISTS learning_resources;")
