"""jobs table

Revision ID: fdf3677895c4
Revises: aeb4039b1e4a
Create Date: 2026-01-16 09:34:08.972065

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fdf3677895c4'
down_revision: Union[str, Sequence[str], None] = 'aeb4039b1e4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
      job_id UUID PRIMARY KEY,
      doc_id UUID,
      job_type TEXT NOT NULL,
      status TEXT NOT NULL,           -- queued/running/succeeded/failed
      attempts INTEGER NOT NULL DEFAULT 0,
      last_error TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_jobs_doc ON jobs(doc_id);")

