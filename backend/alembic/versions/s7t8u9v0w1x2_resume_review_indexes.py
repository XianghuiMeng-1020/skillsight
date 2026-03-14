"""Add indexes and CHECK constraints for resume_reviews, resume_suggestions, resume_templates

Revision ID: s7t8u9v0w1x2
Revises: m6n7o8p9q0r1
Create Date: 2026-03-14

"""
from typing import Sequence, Union

from alembic import op

revision: str = "s7t8u9v0w1x2"
down_revision: Union[str, None] = "m6n7o8p9q0r1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_resume_reviews_user_created ON resume_reviews(user_id, created_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_resume_reviews_doc ON resume_reviews(doc_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_resume_suggestions_review_status ON resume_suggestions(review_id, status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_resume_templates_active ON resume_templates(is_active) WHERE is_active = TRUE;")
    # CHECK constraints for valid enum-like values (only if not already present)
    op.execute("""
        ALTER TABLE resume_reviews
        ADD CONSTRAINT chk_resume_reviews_status
        CHECK (status IN ('scoring', 'reviewed', 'enhanced', 'completed'));
    """)
    op.execute("""
        ALTER TABLE resume_suggestions
        ADD CONSTRAINT chk_resume_suggestions_status
        CHECK (status IN ('pending', 'accepted', 'rejected', 'edited'));
    """)
    op.execute("""
        ALTER TABLE resume_suggestions
        ADD CONSTRAINT chk_resume_suggestions_priority
        CHECK (priority IN ('high', 'medium', 'low'));
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE resume_suggestions DROP CONSTRAINT IF EXISTS chk_resume_suggestions_priority;")
    op.execute("ALTER TABLE resume_suggestions DROP CONSTRAINT IF EXISTS chk_resume_suggestions_status;")
    op.execute("ALTER TABLE resume_reviews DROP CONSTRAINT IF EXISTS chk_resume_reviews_status;")
    op.execute("DROP INDEX IF EXISTS idx_resume_templates_active;")
    op.execute("DROP INDEX IF EXISTS idx_resume_suggestions_review_status;")
    op.execute("DROP INDEX IF EXISTS idx_resume_reviews_doc;")
    op.execute("DROP INDEX IF EXISTS idx_resume_reviews_user_created;")
