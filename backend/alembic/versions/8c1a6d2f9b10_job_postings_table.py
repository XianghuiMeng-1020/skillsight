"""job_postings table

Revision ID: 8c1a6d2f9b10
Revises: fdf3677895c4
Create Date: 2026-04-07
"""
from typing import Sequence, Union

from alembic import op


revision: str = "8c1a6d2f9b10"
down_revision: Union[str, Sequence[str], None] = "fdf3677895c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS job_postings (
            posting_id UUID PRIMARY KEY,
            source_site TEXT NOT NULL,
            source_id TEXT NOT NULL,
            title TEXT NOT NULL,
            company TEXT,
            location TEXT,
            salary TEXT,
            employment_type TEXT,
            posted_at TEXT,
            source_url TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_job_postings_source ON job_postings(source_site, source_id);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_job_postings_snapshot_at ON job_postings(snapshot_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_job_postings_status ON job_postings(status);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS job_postings;")
