"""Expenses, petty cash, and P&L endpoints (Plan/14 B)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.models.expense import Expense, PettyCashTransaction
from app.models.identity import StaffUser
from app.services import expenses as svc
from app.services.settings import get_setting

router = APIRouter(prefix="/api", tags=["expenses"])
editor = Annotated[StaffUser, Depends(require_perm("billing.expense"))]

CATEGORY_HELP = "categories are configured under settings > petty_cash.categories"


def _expense_payload(e: Expense) -> dict:
    return {
        "id": e.id, "category": e.category, "amount": float(e.amount),
        "expense_date": e.expense_date.isoformat(), "note": e.note,
        "paid_from": e.paid_from, "created_by": e.created_by,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@router.get("/expenses")
def list_expenses(
    current: editor, db: DbDep,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: Annotated[date | None, Query()] = None,
    category: str | None = None,
):
    q = select(Expense).where(Expense.is_deleted.is_(False))
    if from_:
        q = q.where(Expense.expense_date >= from_)
    if to:
        q = q.where(Expense.expense_date <= to)
    if category:
        q = q.where(Expense.category == category)
    rows = db.scalars(q.order_by(Expense.expense_date.desc(), Expense.id.desc())).all()
    return {"items": [_expense_payload(e) for e in rows]}


@router.post("/expenses")
def create_expense(
    body: dict, current: editor, request: Request,
    db: DbDep, audit_db: AuditDbDep,
):
    category = str(body.get("category", "")).strip()
    if not category:
        raise AppError("VALIDATION", "category is required")
    try:
        expense_date = date.fromisoformat(body.get("expense_date", ""))
    except (ValueError, TypeError) as exc:
        raise AppError("VALIDATION", "expense_date must be YYYY-MM-DD") from exc
    expense = svc.create_expense(
        db,
        category=category,
        amount=float(body.get("amount", 0)),
        expense_date=expense_date,
        note=body.get("note"),
        paid_from=body.get("paid_from", "petty_cash"),
        actor_id=current.id,
    )
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="expense.create", correlation_id=get_request_id(request),
        entity_type="expense", entity_id=str(expense.id),
        after={"amount": float(expense.amount), "category": expense.category,
               "expense_date": expense.expense_date.isoformat(), "paid_from": expense.paid_from},
    ):
        db.commit()
    return _expense_payload(expense)


@router.patch("/expenses/{expense_id}")
def update_expense(
    expense_id: int, body: dict, current: editor, request: Request,
    db: DbDep, audit_db: AuditDbDep,
):
    expense = db.get(Expense, expense_id)
    if expense is None or expense.is_deleted:
        raise AppError("NOT_FOUND", "expense not found")
    if "note" in body:
        expense.note = body["note"]
    if "category" in body:
        expense.category = str(body["category"]).strip()
    if "expense_date" in body:
        expense.expense_date = date.fromisoformat(body["expense_date"])
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="expense.update", correlation_id=get_request_id(request),
        entity_type="expense", entity_id=str(expense.id),
    ):
        db.commit()
    return _expense_payload(expense)


@router.delete("/expenses/{expense_id}")
def delete_expense_route(
    expense_id: int, current: editor, request: Request,
    db: DbDep, audit_db: AuditDbDep,
):
    expense = db.get(Expense, expense_id)
    if expense is None or expense.is_deleted:
        raise AppError("NOT_FOUND", "expense not found")
    svc.delete_expense(db, expense, current.id)
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="expense.delete", correlation_id=get_request_id(request),
        entity_type="expense", entity_id=str(expense.id),
    ):
        db.commit()
    return {"ok": True}


def _txn_payload(t: PettyCashTransaction) -> dict:
    return {
        "id": t.id, "kind": t.kind, "amount": float(t.amount), "note": t.note,
        "expense_id": t.expense_id, "balance_after": float(t.balance_after),
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.get("/petty-cash/balance")
def get_petty_cash(current: editor, db: DbDep):
    rows = db.scalars(
        select(PettyCashTransaction).order_by(PettyCashTransaction.id.desc()).limit(50)
    ).all()
    return {
        "balance": svc.petty_cash_balance(db),
        "opening_balance": float(get_setting(db, "petty_cash.opening_balance", 0) or 0),
        "transactions": [_txn_payload(t) for t in rows],
    }


@router.post("/petty-cash/{kind}")
def petty_cash_op(
    kind: str, body: dict, current: editor, request: Request,
    db: DbDep, audit_db: AuditDbDep,
):
    svc.petty_cash_op(db, kind, float(body.get("amount", 0)), current.id, body.get("note"))
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action=f"petty_cash.{kind}", correlation_id=get_request_id(request),
        entity_type="petty_cash", entity_id="cash",
        after={"amount": float(body.get("amount", 0))},
    ):
        db.commit()
    return {"balance": svc.petty_cash_balance(db)}


@router.get("/pnl")
def get_pnl(current: editor, db: DbDep, month: str = Query(...)):
    return svc.monthly_pnl(db, month)
