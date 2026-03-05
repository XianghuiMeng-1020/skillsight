"""audit_logs safe migration - no DROP, ALTER only

Revision ID: d1e2f3a4b5c6
Revises: merge_heads_001
Create Date: 2026-02-21

Replaces production-unsafe DROP/CREATE with ALTER to add missing columns.
Existing rows are preserved.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "merge_heads_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure audit_logs exists. If not, create with canonical schema.
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            action TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            object_type TEXT NOT NULL,
            object_id TEXT,
            detail JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    # Add missing columns if table already existed with different schema (no DROP)
    op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS detail JSONB NOT NULL DEFAULT '{}';")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_subject ON audit_logs(subject_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_object ON audit_logs(object_type, object_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at DESC);")


def downgrade() -> None:
    # Downgrade does not drop - safe rollback
    pass
