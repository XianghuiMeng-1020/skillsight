"""course skill review workflow fields

Revision ID: eba96f9bdaa1
Revises: 0a73c1d8b63a
"""

from typing import Sequence, Union
from alembic import op

revision: str = "eba96f9bdaa1"
down_revision: Union[str, None] = "0a73c1d8b63a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE course_skill_map ADD COLUMN IF NOT EXISTS reviewer_subject_id TEXT;")
    op.execute("ALTER TABLE course_skill_map ADD COLUMN IF NOT EXISTS decision TEXT;")  # approved/rejected
    op.execute("ALTER TABLE course_skill_map ADD COLUMN IF NOT EXISTS decision_at TIMESTAMPTZ;")
    op.execute("ALTER TABLE course_skill_map ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;")


def downgrade() -> None:
    op.execute("ALTER TABLE course_skill_map DROP COLUMN IF EXISTS updated_at;")
    op.execute("ALTER TABLE course_skill_map DROP COLUMN IF EXISTS decision_at;")
    op.execute("ALTER TABLE course_skill_map DROP COLUMN IF EXISTS decision;")
    op.execute("ALTER TABLE course_skill_map DROP COLUMN IF EXISTS reviewer_subject_id;")
