"""P4: Protocol 5 - Explainable Change Log tables

Revision ID: c2d3e4f5a6b7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-22

Adds: skill_assessment_snapshots, role_readiness_snapshots, change_log_events
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A) skill_assessment_snapshots - per subject+skill assessment result
    op.execute("""
        CREATE TABLE IF NOT EXISTS skill_assessment_snapshots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            subject_id TEXT NOT NULL,
            skill_id TEXT NOT NULL,
            label TEXT NOT NULL,
            level INTEGER,
            rationale TEXT,
            evidence JSONB NOT NULL DEFAULT '[]',
            request_id TEXT,
            model_info JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_skill_snap_subject_skill ON skill_assessment_snapshots(subject_id, skill_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_skill_snap_created ON skill_assessment_snapshots(created_at DESC);")

    # B) role_readiness_snapshots - per subject+role readiness output
    op.execute("""
        CREATE TABLE IF NOT EXISTS role_readiness_snapshots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            subject_id TEXT NOT NULL,
            role_id TEXT NOT NULL,
            score NUMERIC(5,4) NOT NULL,
            breakdown JSONB NOT NULL DEFAULT '{}',
            request_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_role_snap_subject_role ON role_readiness_snapshots(subject_id, role_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_role_snap_created ON role_readiness_snapshots(created_at DESC);")

    # C) change_log_events - unified explainable change events
    op.execute("""
        CREATE TABLE IF NOT EXISTS change_log_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scope TEXT NOT NULL,
            subject_id TEXT,
            event_type TEXT NOT NULL,
            entity_key TEXT,
            before_state JSONB DEFAULT '{}',
            after_state JSONB DEFAULT '{}',
            diff JSONB DEFAULT '{}',
            why JSONB DEFAULT '{}',
            request_id TEXT,
            actor_role TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_change_log_scope ON change_log_events(scope);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_change_log_subject ON change_log_events(subject_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_change_log_event_type ON change_log_events(event_type);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_change_log_created ON change_log_events(created_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_change_log_request_id ON change_log_events(request_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS change_log_events;")
    op.execute("DROP TABLE IF EXISTS role_readiness_snapshots;")
    op.execute("DROP TABLE IF EXISTS skill_assessment_snapshots;")
