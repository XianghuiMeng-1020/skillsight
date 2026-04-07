"""merge: main chain + mentor_comments_notifications

Revision ID: merge_heads_v2
Revises: t1u2v3w4x5y6, c9d8e7f6a5b4
Create Date: 2026-04-07

"""
from typing import Sequence, Union

revision: str = "merge_heads_v2"
down_revision: Union[str, Sequence[str], None] = ("t1u2v3w4x5y6", "c9d8e7f6a5b4")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
