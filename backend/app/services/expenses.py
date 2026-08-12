"""Expense + petty cash + P&L service (Plan/14 B)."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.billing import Payment
from app.models.expense import Expense, PettyCashTransaction
from app.services.settings import get_setting


def petty_cash_balance(db: Session) -> float:
    """Derived balance = opening + all ins - all outs (B)."""
    opening = float(get_setting(db, "petty_cash.opening_balance", 0) or 0)
    total = db.scalar(
        select(
            func.coalesce(
                func.sum(PettyCashTransaction.amount).filter(PettyCashTransaction.kind == "in"), 0
            )
            - func.coalesce(
                func.sum(PettyCashTransaction.amount).filter(PettyCashTransaction.kind == "out"), 0
            )
        )
    )
    return round(opening + float(total or 0), 2)


def _record_txn(db, kind: str, amount: float, actor_id: int, note=None, expense_id=None):
    amount = round(float(amount), 2)
    txn = PettyCashTransaction(
        kind=kind,
        amount=amount,
        note=note,
        expense_id=expense_id,
        balance_after=petty_cash_balance(db)
        + (amount if kind == "in" else -amount),
        created_by=actor_id,
    )
    db.add(txn)
    return txn


def petty_cash_op(
    db: Session, kind: str, amount: float, actor_id: int, note: str | None = None
) -> PettyCashTransaction:
    if kind not in ("in", "out"):
        raise AppError("VALIDATION", "kind must be in or out")
    if amount <= 0:
        raise AppError("VALIDATION", "amount must be positive")
    if kind == "out" and petty_cash_balance(db) < amount:
        raise AppError("VALIDATION", "insufficient petty cash balance")
    return _record_txn(db, kind, amount, actor_id, note)


def create_expense(
    db: Session, *, category: str, amount: float, expense_date: date,
    actor_id: int, note: str | None = None, paid_from: str = "petty_cash",
) -> Expense:
    if paid_from not in ("petty_cash", "bank"):
        raise AppError("VALIDATION", "paid_from must be petty_cash or bank")
    if amount <= 0:
        raise AppError("VALIDATION", "amount must be positive")
    expense = Expense(
        category=category, amount=round(amount, 2), expense_date=expense_date,
        note=note, paid_from=paid_from, created_by=actor_id,
    )
    db.add(expense)
    db.flush()
    if paid_from == "petty_cash":
        if petty_cash_balance(db) < float(expense.amount):
            raise AppError(
                "VALIDATION",
                f"petty cash balance ({petty_cash_balance(db):.2f}) "
                "is less than the expense amount",
            )
        _record_txn(db, "out", expense.amount, actor_id, f"expense: {category}", expense.id)
    return expense


def delete_expense(db: Session, expense: Expense, actor_id: int) -> None:
    """Soft delete; a petty-cash expense is reversed by a compensating in-txn."""
    expense.is_deleted = True
    if expense.paid_from == "petty_cash":
        _record_txn(db, "in", expense.amount, actor_id, f"reversal: {expense.category}", expense.id)


def monthly_pnl(db: Session, month: str) -> dict:
    """Cash-basis P&L: collected revenue - refunds - expenses for a calendar month."""
    try:
        start = date.fromisoformat(f"{month}-01")
    except ValueError as exc:
        raise AppError("VALIDATION", "month must be YYYY-MM") from exc
    end = (
        date(start.year + 1, 1, 1)
        if start.month == 12
        else date(start.year, start.month + 1, 1)
    )
    payments = db.scalars(
        select(Payment).where(Payment.paid_at >= start, Payment.paid_at < end)
    ).all()
    revenue = round(sum(float(p.amount) for p in payments if not p.is_refund), 2)
    refunds = round(sum(float(p.amount) for p in payments if p.is_refund), 2)
    expenses = db.scalars(
        select(Expense).where(
            Expense.expense_date >= start,
            Expense.expense_date < end,
            Expense.is_deleted.is_(False),
        )
    ).all()
    total_expenses = round(sum(float(e.amount) for e in expenses), 2)
    return {
        "month": month,
        "revenue": revenue,
        "refunds": refunds,
        "expenses": total_expenses,
        "net": round(revenue - refunds - total_expenses, 2),
    }
