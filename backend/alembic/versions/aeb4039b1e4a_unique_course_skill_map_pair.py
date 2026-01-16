"""unique course-skill map pair

Revision ID: aeb4039b1e4a
Revises: eba96f9bdaa1
Create Date: 2026-01-16 08:28:15.014528

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aeb4039b1e4a'
down_revision: Union[str, Sequence[str], None] = 'eba96f9bdaa1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_course_skill_pair ON course_skill_map(course_id, skill_id);")

