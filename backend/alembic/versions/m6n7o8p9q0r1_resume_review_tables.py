"""resume_reviews, resume_suggestions, resume_templates for Resume Enhancement Center

Revision ID: m6n7o8p9q0r1
Revises: k5l6m7n8o9p0
Create Date: 2026-03-13

"""
from typing import Sequence, Union

from alembic import op

revision: str = "m6n7o8p9q0r1"
down_revision: Union[str, None] = "k5l6m7n8o9p0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS resume_reviews (
            review_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         TEXT NOT NULL,
            doc_id          TEXT NOT NULL,
            target_role_id  TEXT,
            status          TEXT NOT NULL DEFAULT 'scoring',
            initial_scores   JSONB,
            final_scores     JSONB,
            total_initial    DOUBLE PRECISION,
            total_final      DOUBLE PRECISION,
            accepted_count   INTEGER DEFAULT 0,
            rejected_count   INTEGER DEFAULT 0,
            template_id     TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_resume_reviews_user ON resume_reviews(user_id);")

    op.execute("""
        CREATE TABLE IF NOT EXISTS resume_suggestions (
            suggestion_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            review_id       UUID NOT NULL REFERENCES resume_reviews(review_id) ON DELETE CASCADE,
            dimension       TEXT NOT NULL,
            section         TEXT,
            original_text   TEXT,
            suggested_text  TEXT,
            explanation     TEXT,
            priority        TEXT NOT NULL DEFAULT 'medium',
            status          TEXT NOT NULL DEFAULT 'pending',
            student_edit    TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_resume_suggestions_review ON resume_suggestions(review_id);")

    op.execute("""
        CREATE TABLE IF NOT EXISTS resume_templates (
            template_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name            TEXT NOT NULL,
            description     TEXT,
            industry_tags   JSONB DEFAULT '[]'::jsonb,
            preview_url     TEXT,
            template_data   JSONB,
            template_file   TEXT,
            is_active       BOOLEAN DEFAULT TRUE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS resume_suggestions;")
    op.execute("DROP TABLE IF EXISTS resume_reviews;")
    op.execute("DROP TABLE IF EXISTS resume_templates;")
