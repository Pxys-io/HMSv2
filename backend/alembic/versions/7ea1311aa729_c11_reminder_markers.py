"""c11: reminder markers

Revision ID: 7ea1311aa729
Revises: 94e67e91c859
Create Date: 2026-08-12 03:32:42.356469

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ea1311aa729'
down_revision: Union[str, None] = '94e67e91c859'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('appointment',
                  sa.Column('reminder_sms_sent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('appointment',
                  sa.Column('reminder_email_sent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('appointment', 'reminder_email_sent_at')
    op.drop_column('appointment', 'reminder_sms_sent_at')
