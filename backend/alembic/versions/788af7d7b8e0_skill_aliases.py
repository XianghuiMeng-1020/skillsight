"""skill aliases

Revision ID: 788af7d7b8e0
Revises: 0de407bd396f
Create Date: 2026-01-15 22:40:54.264916

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '788af7d7b8e0'
down_revision: Union[str, Sequence[str], None] = '0de407bd396f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
