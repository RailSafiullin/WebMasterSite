"""Add sequences for query and url table column id

Revision ID: d89d3d74cdda
Revises: 54583e7252cc
Create Date: 2024-10-08 22:18:20.232633

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd89d3d74cdda'
down_revision = '54583e7252cc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.execute("ALTER TABLE query ALTER COLUMN id SET DEFAULT nextval('query_id_seq')")
    op.execute("ALTER TABLE url ALTER COLUMN id SET DEFAULT nextval('url_id_seq')")
    # ### end Alembic commands ###
def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.execute("ALTER TABLE query ALTER COLUMN id DROP DEFAULT")
    op.execute("ALTER TABLE url ALTER COLUMN id DROP DEFAULT")
    # ### end Alembic commands ###
