"""c8: duplicate groups

Revision ID: d6773a6a237c
Revises: b8714996dcc0
Create Date: 2026-08-12 03:15:44.532636

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6773a6a237c'
down_revision: Union[str, None] = 'b8714996dcc0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'duplicate_group',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('primary_profile_id', sa.Integer(), nullable=False),
        sa.Column('profile_ids', sa.JSON(), nullable=False),
        sa.Column('match_reason', sa.String(length=120), nullable=False),
        sa.Column('status', sa.Enum('open', 'merged', 'rejected', name='duplicate_status'),
                  nullable=False),
        sa.Column('resolved_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['primary_profile_id'], ['patient_profile.id']),
        sa.ForeignKeyConstraint(['resolved_by'], ['staff_user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_duplicate_group_status'), 'duplicate_group', ['status'],
                    unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_duplicate_group_status'), table_name='duplicate_group')
    op.drop_table('duplicate_group')
