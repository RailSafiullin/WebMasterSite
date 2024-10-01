"""add_user_id_as_integer

Revision ID: 69ca132e5e49
Revises: 4920427f03ac
Create Date: 2024-10-01 14:13:10.287578

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '69ca132e5e49'
down_revision: Union[str, None] = '4920427f03ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('config', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'config', 'user', ['user_id'], ['id'])
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'config', type_='foreignkey')
    op.drop_column('config', 'user_id')
    # ### end Alembic commands ###
