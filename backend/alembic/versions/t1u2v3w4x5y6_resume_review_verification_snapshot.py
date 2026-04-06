"""Add verification snapshot columns to resume_reviews

Revision ID: t1u2v3w4x5y6
Revises: s7t8u9v0w1x2
Create Date: 2026-04-06
"""
from typing import Sequence, Union

from alembic import op

revision: str = "t1u2v3w4x5y6"
down_revision: Union[str, None] = "s7t8u9v0w1x2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE resume_reviews
        ADD COLUMN IF NOT EXISTS verification_snapshot JSONB;
        """
    )
    op.execute(
        """
        ALTER TABLE resume_reviews
        ADD COLUMN IF NOT EXISTS verification_version TEXT;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE resume_reviews DROP COLUMN IF EXISTS verification_version;")
    op.execute("ALTER TABLE resume_reviews DROP COLUMN IF EXISTS verification_snapshot;")

