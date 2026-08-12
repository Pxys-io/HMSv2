"""rx route

Revision ID: 4c2793206c9d
Revises: ecaf63850de2
Create Date: 2026-08-12 04:42:40.521637

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c2793206c9d'
down_revision: Union[str, None] = 'ecaf63850de2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('prescription_item',
                  sa.Column('route', sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column('prescription_item', 'route')
