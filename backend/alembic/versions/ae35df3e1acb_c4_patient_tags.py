"""c4: patient tags

Revision ID: ae35df3e1acb
Revises: f20195d56379
Create Date: 2026-08-12 02:55:54.131819

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ae35df3e1acb'
down_revision: Union[str, None] = 'f20195d56379'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'patient_tag_def',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('name_ar', sa.String(length=60), nullable=True),
        sa.Column('color', sa.String(length=7), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table(
        'patient_tag',
        sa.Column('patient_profile_id', sa.Integer(), nullable=False),
        sa.Column('tag_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['patient_profile_id'], ['patient_profile.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['patient_tag_def.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('patient_profile_id', 'tag_id'),
    )


def downgrade() -> None:
    op.drop_table('patient_tag')
    op.drop_table('patient_tag_def')
