"""Expenses + petty cash (Plan/14 B)."""

from datetime import date

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Expense(TimestampMixin, Base):
    __tablename__ = "expense"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    expense_date: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_from: Mapped[str] = mapped_column(
        Enum("petty_cash", "bank", name="expense_source"), default="petty_cash"
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("staff_user.id"))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class PettyCashTransaction(TimestampMixin, Base):
    __tablename__ = "petty_cash_transaction"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(
        Enum("in", "out", name="petty_cash_kind"), index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    expense_id: Mapped[int | None] = mapped_column(
        ForeignKey("expense.id"), nullable=True
    )
    balance_after: Mapped[float] = mapped_column(Numeric(12, 2))
    created_by: Mapped[int] = mapped_column(ForeignKey("staff_user.id"))
