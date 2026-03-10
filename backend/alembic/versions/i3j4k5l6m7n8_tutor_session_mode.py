"""Add mode column to tutor_dialogue_sessions for assessment vs resume_review

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-03-10

"""
from typing import Sequence, Union

from alembic import op

revision: str = "i3j4k5l6m7n8"
down_revision: Union[str, None] = "h2i3j4k5l6m7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE tutor_dialogue_sessions
        ADD COLUMN IF NOT EXISTS mode TEXT DEFAULT 'assessment'
    """)
    op.execute("""
        UPDATE tutor_dialogue_sessions SET mode = 'assessment' WHERE mode IS NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE tutor_dialogue_sessions DROP COLUMN IF EXISTS mode")
