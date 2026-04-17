"""Concept graph (skill_aliases + skill_adjacency) and match_feedback

Revision ID: u8v9w0x1y2z3
Revises: merge_heads_v2
Create Date: 2026-04-17

Adds three tables that power the unified role-match scorer:

* ``skill_aliases``     — free-text label -> canonical concept resolution
                          (DB-driven complement to the in-code defaults).
* ``skill_adjacency``   — directional transferable-skill graph powering
                          partial credit when a student demonstrates an
                          adjacent skill instead of the exact requirement.
* ``match_feedback``    — captures per-user thumbs up/down on each role
                          match recommendation.  Foundation for future
                          threshold calibration against ground-truth.

All three are additive and idempotent.  The application layer falls back
to hard-coded defaults when these tables don't exist yet, so deploying
the code before running this migration cannot break production.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "u8v9w0x1y2z3"
down_revision: Union[str, Sequence[str], None] = "merge_heads_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_aliases (
            alias_id    SERIAL PRIMARY KEY,
            label       TEXT NOT NULL,
            canonical   TEXT NOT NULL,
            source      TEXT NOT NULL DEFAULT 'manual',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT skill_aliases_label_unique UNIQUE (label)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_skill_aliases_canonical "
        "ON skill_aliases(canonical);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_adjacency (
            edge_id      SERIAL PRIMARY KEY,
            from_concept TEXT NOT NULL,
            to_concept   TEXT NOT NULL,
            weight       REAL NOT NULL CHECK (weight > 0 AND weight <= 1),
            source       TEXT NOT NULL DEFAULT 'manual',
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT skill_adjacency_unique_edge
                UNIQUE (from_concept, to_concept)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_skill_adjacency_from "
        "ON skill_adjacency(from_concept);"
    )

    # match_feedback — ground truth signal for future calibration.
    # role_id is intentionally TEXT (not FK) so JD-derived live job
    # match feedback can use it too without joining to roles.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS match_feedback (
            feedback_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            subject_id   TEXT NOT NULL,
            role_id      TEXT NOT NULL,
            verdict      TEXT NOT NULL CHECK (verdict IN ('good', 'bad', 'unsure')),
            readiness    REAL,
            match_class  TEXT,
            note         TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_match_feedback_subject "
        "ON match_feedback(subject_id, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_match_feedback_role "
        "ON match_feedback(role_id, verdict);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS match_feedback;")
    op.execute("DROP TABLE IF EXISTS skill_adjacency;")
    op.execute("DROP TABLE IF EXISTS skill_aliases;")
