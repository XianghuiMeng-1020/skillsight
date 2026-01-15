"""courses and course_skill_map

Revision ID: cf8499c65090
Revises: 3cc452c8eafa
"""

from typing import Sequence, Union
from alembic import op

revision: str = "cf8499c65090"
down_revision: Union[str, None] = "3cc452c8eafa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS courses (
      course_id TEXT PRIMARY KEY,
      course_code TEXT NOT NULL,
      title TEXT NOT NULL,
      description TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("""CREATE INDEX IF NOT EXISTS idx_courses_code ON courses(course_code);""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS course_skill_map (
      map_id UUID PRIMARY KEY,
      course_id TEXT NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
      skill_id TEXT NOT NULL,
      intended_level INTEGER,
      evidence_type TEXT,
      status TEXT NOT NULL DEFAULT 'pending',
      note TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ
    );
    """)
    op.execute("""CREATE INDEX IF NOT EXISTS idx_course_skill_course ON course_skill_map(course_id);""")
    op.execute("""CREATE INDEX IF NOT EXISTS idx_course_skill_skill ON course_skill_map(skill_id);""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS course_skill_map;")
    op.execute("DROP TABLE IF EXISTS courses;")
