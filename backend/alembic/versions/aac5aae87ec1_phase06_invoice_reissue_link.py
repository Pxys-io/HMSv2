"""phase06: invoice reissue link

Revision ID: aac5aae87ec1
Revises: 703dd3d08dc7
Create Date: 2026-08-11 00:45:14.812465

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aac5aae87ec1'
down_revision: Union[str, None] = 'd91b6d39bb4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("invoice") as batch:
        batch.add_column(sa.Column("reissue_of_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_invoice_reissue_of", "invoice", ["reissue_of_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("invoice") as batch:
        batch.drop_constraint("fk_invoice_reissue_of", type_="foreignkey")
        batch.drop_column("reissue_of_id")
