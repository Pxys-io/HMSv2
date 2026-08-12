"""HR endpoints: attendance, leaves, payroll (Plan/14 F)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.models.hr import AttendanceRecord, LeaveRequest, PayrollLineItem, PayrollRun
from app.models.identity import StaffUser
from app.services.settings import clinic_now, clinic_today

router = APIRouter(prefix="/api/hr", tags=["hr"])
attendee = Annotated[StaffUser, Depends(require_perm("hr.attendance"))]
manager = Annotated[StaffUser, Depends(require_perm("hr.leave"))]
payroller = Annotated[StaffUser, Depends(require_perm("hr.payroll"))]


def _leave_payload(leave: LeaveRequest) -> dict:
    return {
        "id": leave.id, "staff_user_id": leave.staff_user_id,
        "leave_type": leave.leave_type,
        "from_date": leave.from_date.isoformat(), "to_date": leave.to_date.isoformat(),
        "days": float(leave.days), "reason": leave.reason, "status": leave.status,
        "decided_by": leave.decided_by,
        "decided_at": leave.decided_at.isoformat() if leave.decided_at else None,
        "created_at": leave.created_at.isoformat() if leave.created_at else None,
    }


# ------------------------------------------------------------- attendance


@router.post("/attendance/clock-in")
def clock_in(current: attendee, request: Request, db: DbDep, audit_db: AuditDbDep):
    now = clinic_now()
    existing = db.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.staff_user_id == current.id,
            AttendanceRecord.date == now.date(),
        )
    )
    if existing is not None and existing.check_out is None:
        raise AppError("VALIDATION", "already checked in")
    record = AttendanceRecord(staff_user_id=current.id, date=now.date(), check_in=now)
    db.add(record)
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="hr.clock_in", correlation_id=get_request_id(request),
        entity_type="attendance", entity_id=str(record.id),
    ):
        db.commit()
    return {"date": now.date().isoformat(), "check_in": now.isoformat()}


@router.post("/attendance/clock-out")
def clock_out(current: attendee, request: Request, db: DbDep, audit_db: AuditDbDep):
    now = clinic_now()
    record = db.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.staff_user_id == current.id,
            AttendanceRecord.date == now.date(),
        )
    )
    if record is None or record.check_out is not None:
        raise AppError("VALIDATION", "no open attendance record today")
    record.check_out = now
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="hr.clock_out", correlation_id=get_request_id(request),
        entity_type="attendance", entity_id=str(record.id),
    ):
        db.commit()
    return {"date": now.date().isoformat(), "check_out": now.isoformat()}


@router.get("/attendance")
def list_attendance(current: attendee, db: DbDep, month: str = Query(...)):
    try:
        start = date.fromisoformat(f"{month}-01")
    except ValueError as exc:
        raise AppError("VALIDATION", "month must be YYYY-MM") from exc
    end = (
        date(start.year + 1, 1, 1) if start.month == 12
        else date(start.year, start.month + 1, 1)
    )
    rows = db.scalars(
        select(AttendanceRecord).where(
            AttendanceRecord.date >= start, AttendanceRecord.date < end
        ).order_by(AttendanceRecord.date, AttendanceRecord.staff_user_id)
    ).all()
    return {"items": [
        {"id": r.id, "staff_user_id": r.staff_user_id, "date": r.date.isoformat(),
         "check_in": r.check_in.isoformat(),
         "check_out": r.check_out.isoformat() if r.check_out else None}
        for r in rows
    ]}


# ------------------------------------------------------------- leaves


@router.get("/leaves")
def list_leaves(current: manager, db: DbDep, status: str | None = None):
    stmt = select(LeaveRequest).order_by(LeaveRequest.id.desc())
    if status:
        stmt = stmt.where(LeaveRequest.status == status)
    rows = db.scalars(stmt).all()
    return {"items": [_leave_payload(r) for r in rows]}


def _calc_days(from_date: date, to_date: date) -> float:
    if to_date < from_date:
        raise AppError("VALIDATION", "to_date must be >= from_date")
    return (to_date - from_date).days + 1


@router.post("/leaves")
def apply_leave(
    body: dict, current: attendee, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    from_date = date.fromisoformat(str(body.get("from_date", "")))
    to_date = date.fromisoformat(str(body.get("to_date", "")))
    leave = LeaveRequest(
        staff_user_id=current.id,
        leave_type=str(body.get("leave_type", "annual")).strip() or "annual",
        from_date=from_date, to_date=to_date,
        days=_calc_days(from_date, to_date),
        reason=body.get("reason"),
        status="pending",
    )
    db.add(leave)
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="hr.leave.apply", correlation_id=get_request_id(request),
        entity_type="leave", entity_id="0",
        after={"from": from_date.isoformat(), "to": to_date.isoformat()},
    ):
        db.commit()
    return _leave_payload(leave)


@router.patch("/leaves/{leave_id}")
def decide_leave(
    leave_id: int, body: dict, current: manager, request: Request,
    db: DbDep, audit_db: AuditDbDep,
):
    leave = db.get(LeaveRequest, leave_id)
    if leave is None:
        raise AppError("NOT_FOUND", "leave request not found")
    new_status = body.get("status")
    if new_status not in ("approved", "rejected", "cancelled"):
        raise AppError("VALIDATION", "status must be approved/rejected/cancelled")
    # F2: terminal states — approved cannot be rejected afterwards
    if leave.status == "approved" and new_status == "rejected":
        raise AppError("VALIDATION", "an approved leave cannot be rejected")
    leave.status = new_status
    leave.decided_by = current.id
    leave.decided_at = clinic_now()
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action=f"hr.leave.{new_status}", correlation_id=get_request_id(request),
        entity_type="leave", entity_id=str(leave_id),
    ):
        db.commit()
    return _leave_payload(leave)


@router.get("/leave-balances")
def leave_balances(current: manager, db: DbDep, year: int | None = None):
    """F5: days taken per type this year from approved leaves."""
    year = year or clinic_today().year
    rows = db.scalars(select(LeaveRequest).where(
        LeaveRequest.status == "approved",
        LeaveRequest.from_date >= date(year, 1, 1),
        LeaveRequest.from_date <= date(year, 12, 31),
    )).all()
    totals: dict[str, float] = {}
    for r in rows:
        totals[r.leave_type] = round(totals.get(r.leave_type, 0) + float(r.days), 1)
    return {"year": year, "balances": totals}


# ------------------------------------------------------------- payroll


@router.post("/payroll/run")
def run_payroll(
    body: dict, current: payroller, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    month = str(body.get("month", ""))
    try:
        date.fromisoformat(f"{month}-01")
    except ValueError as exc:
        raise AppError("VALIDATION", "month must be YYYY-MM") from exc
    existing = db.scalar(select(PayrollRun).where(PayrollRun.month == month))
    if existing:
        raise AppError("CONFLICT", f"payroll for {month} already exists")
    staff = db.scalars(
        select(StaffUser).where(StaffUser.is_active.is_(True))
    ).all()
    run = PayrollRun(month=month, status="draft", generated_by=current.id)
    db.add(run)
    db.flush()
    for user in staff:
        base = round(float(user.base_salary or 0), 2)
        allowances = round(float(user.allowances or 0), 2)
        deductions = round(float(user.deductions or 0), 2)
        gross = round(base + allowances - deductions, 2)
        tax = round(gross * float(user.tax_pct or 0) / 100, 2)
        social = round(float(user.social_insurance or 0), 2)
        net = round(gross - tax - social, 2)
        db.add(PayrollLineItem(
            payroll_run_id=run.id, staff_user_id=user.id,
            base_salary=base, allowances=allowances, deductions=deductions,
            gross=gross, tax=tax, social_insurance=social, net=net,
        ))
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="hr.payroll.run", correlation_id=get_request_id(request),
        entity_type="payroll", entity_id=str(run.id), after={"month": month},
    ):
        db.commit()
    return _payroll_payload(db, run)


def _payroll_payload(db: Session, run: PayrollRun) -> dict:
    return {
        "id": run.id, "month": run.month, "status": run.status,
        "generated_by": run.generated_by,
        "generated_at": run.created_at.isoformat() if run.created_at else None,
        "items": [
            {"id": i.id, "staff_user_id": i.staff_user_id,
             "base_salary": float(i.base_salary), "allowances": float(i.allowances),
             "deductions": float(i.deductions), "gross": float(i.gross),
             "tax": float(i.tax), "social_insurance": float(i.social_insurance),
             "net": float(i.net)}
            for i in run.items
        ],
    }


@router.get("/payroll")
def get_payroll(current: payroller, db: DbDep, month: str = Query(...)):
    run = db.scalar(select(PayrollRun).where(PayrollRun.month == month))
    if run is None:
        raise AppError("NOT_FOUND", f"no payroll for {month}")
    return _payroll_payload(db, run)
