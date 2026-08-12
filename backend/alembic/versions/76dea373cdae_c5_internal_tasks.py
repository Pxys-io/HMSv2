"""c5: internal tasks

Revision ID: 76dea373cdae
Revises: ae35df3e1acb
Create Date: 2026-08-12 03:00:24.279932

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '76dea373cdae'
down_revision: Union[str, None] = 'ae35df3e1acb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'task',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('due_at', sa.Date(), nullable=True),
        sa.Column('assigned_to', sa.Integer(), nullable=True),
        sa.Column('priority', sa.Enum('low', 'medium', 'high', name='task_priority'),
                  nullable=False),
        sa.Column('status', sa.Enum('open', 'in_progress', 'done', name='task_status'),
                  nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['assigned_to'], ['staff_user.id']),
        sa.ForeignKeyConstraint(['created_by'], ['staff_user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_task_assigned_to'), 'task', ['assigned_to'], unique=False)
    op.create_index(op.f('ix_task_due_at'), 'task', ['due_at'], unique=False)
    op.create_index(op.f('ix_task_status'), 'task', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_task_status'), table_name='task')
    op.drop_index(op.f('ix_task_due_at'), table_name='task')
    op.drop_index(op.f('ix_task_assigned_to'), table_name='task')
    op.drop_table('task')
