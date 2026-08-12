"""b: expenses + petty cash

Revision ID: 71e68b362576
Revises: cd3ba9650c1d
Create Date: 2026-08-12 02:22:26.620474

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '71e68b362576'
down_revision: Union[str, None] = 'cd3ba9650c1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expense",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "paid_from",
            sa.Enum("petty_cash", "bank", name="expense_source"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["staff_user.id"]),
    )
    op.create_index("ix_expense_category", "expense", ["category"])
    op.create_index("ix_expense_expense_date", "expense", ["expense_date"])

    op.create_table(
        "petty_cash_transaction",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "kind",
            sa.Enum("in", "out", name="petty_cash_kind"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("expense_id", sa.Integer(), nullable=True),
        sa.Column("balance_after", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["staff_user.id"]),
        sa.ForeignKeyConstraint(["expense_id"], ["expense.id"]),
    )
    op.create_index("ix_petty_cash_transaction_kind", "petty_cash_transaction", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_petty_cash_transaction_kind", table_name="petty_cash_transaction")
    op.drop_table("petty_cash_transaction")
    op.drop_index("ix_expense_expense_date", table_name="expense")
    op.drop_index("ix_expense_category", table_name="expense")
    op.drop_table("expense")
