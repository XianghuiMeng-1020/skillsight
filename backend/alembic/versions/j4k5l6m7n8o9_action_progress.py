"""Add action_progress table for tracking action completion (Gap 7)

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-03-10

"""
from typing import Sequence, Union

from alembic import op

revision: str = "j4k5l6m7n8o9"
down_revision: Union[str, None] = "i3j4k5l6m7n8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS action_progress (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL,
            skill_id TEXT NOT NULL,
            gap_type TEXT NOT NULL,
            role_id TEXT,
            doc_id UUID,
            action_title TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(user_id, skill_id, gap_type)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_action_progress_user ON action_progress(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_action_progress_status ON action_progress(status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS action_progress")
