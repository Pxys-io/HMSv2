"""phase-billing: visit type categories and custom names

Revision ID: 55cbd38d8a58
Revises: 2a7dbb4d3c67
Create Date: 2026-08-12 00:29:45.666169

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '55cbd38d8a58'
down_revision: Union[str, None] = '2a7dbb4d3c67'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("visit") as batch:
        batch.add_column(sa.Column("custom_type_name", sa.String(length=200), nullable=True))
    with op.batch_alter_table("visit_type") as batch:
        batch.add_column(
            sa.Column(
                "category",
                sa.Enum("new_visit", "follow_up", "procedure", "other", name="visit_type_category"),
                nullable=False,
                server_default="other",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("visit_type") as batch:
        batch.drop_column("category")
    with op.batch_alter_table("visit") as batch:
        batch.drop_column("custom_type_name")
