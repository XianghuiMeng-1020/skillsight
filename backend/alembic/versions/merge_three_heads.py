"""Merge three heads (5b2b7a1c0b0d, 9c1e2f4a7b10, b1c2d3e4f5a6)

Revision ID: merge_heads_001
Revises: 5b2b7a1c0b0d, 9c1e2f4a7b10, b1c2d3e4f5a6
Create Date: 2026-02-20

"""
from typing import Sequence, Union

from alembic import op


revision: str = "merge_heads_001"
down_revision: Union[str, Sequence[str], None] = ("5b2b7a1c0b0d", "9c1e2f4a7b10", "b1c2d3e4f5a6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Merge migration - no schema changes, just unifies heads
    pass


def downgrade() -> None:
    pass
