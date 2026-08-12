"""form assets

Revision ID: 40c7277d3c06
Revises: 4c2793206c9d
Create Date: 2026-08-12 12:20:30.130717

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '40c7277d3c06'
down_revision: Union[str, None] = '4c2793206c9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('custom_field',
                  sa.Column('template_file_id', sa.Integer(), nullable=True))
    op.create_table(
        'form_asset_template',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('rel_path', sa.String(length=500), nullable=False),
        sa.Column('mime', sa.String(length=120), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['uploaded_by'], ['staff_user.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('form_asset_template')
    op.drop_column('custom_field', 'template_file_id')
