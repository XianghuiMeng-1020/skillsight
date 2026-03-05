"""audit_logs: add request_id, status, error for middleware (P1)

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-02-21

Safe: ADD COLUMN IF NOT EXISTS only. No DROP.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS request_id TEXT;")
    op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS status TEXT;")
    op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS error TEXT;")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_request_id ON audit_logs(request_id);")


def downgrade() -> None:
    pass
