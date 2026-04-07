"""mentor comments and notifications tables

Revision ID: c9d8e7f6a5b4
Revises: 8c1a6d2f9b10
Create Date: 2026-04-07
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c9d8e7f6a5b4"
down_revision: Union[str, Sequence[str], None] = "8c1a6d2f9b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mentor_comments (
            comment_id UUID PRIMARY KEY,
            subject_id TEXT NOT NULL,
            skill_id TEXT NOT NULL,
            comment TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_mentor_comments_subject_skill ON mentor_comments(subject_id, skill_id, created_at DESC);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            notification_id UUID PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            source_url TEXT,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user_created ON notifications(user_id, created_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(user_id, is_read, created_at DESC);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notifications;")
    op.execute("DROP TABLE IF EXISTS mentor_comments;")
