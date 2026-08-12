"""c10: shared documents

Revision ID: 94e67e91c859
Revises: d6773a6a237c
Create Date: 2026-08-12 03:26:00.707112

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '94e67e91c859'
down_revision: Union[str, None] = 'd6773a6a237c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('visit', sa.Column('documents_shared', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('visit', 'documents_shared')
