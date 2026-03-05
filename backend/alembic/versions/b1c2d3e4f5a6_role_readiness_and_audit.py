"""role_readiness and audit_logs tables

Revision ID: b1c2d3e4f5a6
Revises: fdf3677895c4
Create Date: 2026-01-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'fdf3677895c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create role_readiness table for Decision 4
    op.execute("""
    CREATE TABLE IF NOT EXISTS role_readiness (
        readiness_id UUID PRIMARY KEY,
        doc_id TEXT NOT NULL,
        role_id TEXT NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
        score NUMERIC NOT NULL DEFAULT 0,
        status_summary JSONB NOT NULL DEFAULT '{}',
        items JSONB NOT NULL DEFAULT '[]',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_role_readiness_doc ON role_readiness(doc_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_role_readiness_role ON role_readiness(role_id);")
    
    # Create audit_logs table for Protocol 8 (safe: no DROP - use CREATE IF NOT EXISTS)
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_subject ON audit_logs(subject_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_object ON audit_logs(object_type, object_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at DESC);")
    
    # Create consents table if not exists (Protocol 09); then add missing columns for older schemas
    op.execute("""
    CREATE TABLE IF NOT EXISTS consents (
        consent_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id TEXT NOT NULL,
        doc_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'granted',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        revoked_at TIMESTAMPTZ,
        revoke_reason TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_consents_user ON consents(user_id);
    CREATE INDEX IF NOT EXISTS idx_consents_doc ON consents(doc_id);
    CREATE INDEX IF NOT EXISTS idx_consents_status ON consents(status);
    """)
    op.execute("""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'consents') THEN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'consents' AND column_name = 'consent_id') THEN
                ALTER TABLE consents ADD COLUMN consent_id UUID;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'consents' AND column_name = 'revoked_at') THEN
                ALTER TABLE consents ADD COLUMN revoked_at TIMESTAMPTZ;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'consents' AND column_name = 'revoke_reason') THEN
                ALTER TABLE consents ADD COLUMN revoke_reason TEXT;
            END IF;
        END IF;
    END $$;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS role_readiness CASCADE;")
    op.execute("DROP TABLE IF EXISTS audit_logs CASCADE;")
