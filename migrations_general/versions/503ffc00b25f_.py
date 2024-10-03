"""empty message

Revision ID: 503ffc00b25f
Revises: 292230311e1f, 645aceed0889
Create Date: 2024-10-03 20:09:20.336711

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '503ffc00b25f'
down_revision: Union[str, None] = ('292230311e1f', '645aceed0889')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
