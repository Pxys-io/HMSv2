"""c2: activity stream

Revision ID: 27c49033a18d
Revises: 71e68b362576
Create Date: 2026-08-12 02:36:24.867361

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '27c49033a18d'
down_revision: Union[str, None] = '71e68b362576'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_profile_id", sa.Integer(), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_label", sa.String(length=200), nullable=True),
        sa.Column("type", sa.String(length=60), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["patient_profile_id"], ["patient_profile.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_activity_event_patient_profile_id", "activity_event", ["patient_profile_id"])
    op.create_index("ix_activity_event_type", "activity_event", ["type"])


def downgrade() -> None:
    op.drop_index("ix_activity_event_type", table_name="activity_event")
    op.drop_index("ix_activity_event_patient_profile_id", table_name="activity_event")
    op.drop_table("activity_event")
