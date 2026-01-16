"""skill aliases table

Revision ID: 0de407bd396f
Revises: cf8499c65090
Create Date: 2026-01-15 22:40:05.919732

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0de407bd396f'
down_revision: Union[str, Sequence[str], None] = 'cf8499c65090'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
