"""empty message

Revision ID: ba2bf933322a
Revises: 1d0e44087d2d, 3d33bdef2e5f
Create Date: 2024-10-04 12:28:34.447272

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba2bf933322a'
down_revision: Union[str, None] = ('1d0e44087d2d', '3d33bdef2e5f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
