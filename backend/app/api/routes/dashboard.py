"""Dashboard + KPI endpoints (Plan/14 C1)."""

from datetime import date, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.core.deps import DbDep, require_perm
from app.core.errors import AppError
from app.models.billing import Invoice, Payment
from app.models.emr import Visit
from app.models.identity import PatientProfile, StaffUser
from app.models.queueing import QueueEntry
from app.models.scheduling import Appointment
from app.services.settings import clinic_today

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
viewer = Annotated[StaffUser, Depends(require_perm("ops.dashboard"))]

OPEN_STATUSES = ("waiting", "called", "in_room")


@router.get("/overview")
def overview(current: viewer, db: DbDep):
    """Today's headline numbers for the ops dashboard."""
    day = clinic_today()
    seen = db.scalar(
        select(func.count()).select_from(QueueEntry).where(
            QueueEntry.date == day, QueueEntry.status == "completed"
        )
    )
    waiting = db.scalar(
        select(func.count()).select_from(QueueEntry).where(
            QueueEntry.date == day, QueueEntry.status.in_(OPEN_STATUSES)
        )
    )
    start = datetime.combine(day, time.min)
    end = datetime.combine(day, time.max)
    payments = db.scalars(
        select(Payment).where(Payment.paid_at >= start, Payment.paid_at <= end)
    ).all()
    revenue = round(
        sum(float(p.amount) for p in payments if not p.is_refund)
        - sum(float(p.amount) for p in payments if p.is_refund),
        2,
    )
    uncollected = db.scalar(
        select(func.coalesce(func.sum(Invoice.patient_due), 0)).where(
            Invoice.status != "cancelled", Invoice.patient_due > 0
        )
    )
    return {
        "date": day.isoformat(),
        "seen": seen or 0,
        "waiting": waiting or 0,
        "revenue_today": revenue,
        "uncollected": float(uncollected or 0),
    }


@router.get("/kpis")
def kpis(current: viewer, db: DbDep, from_date: Annotated[date, Query(alias="from")],
         to_date: Annotated[date, Query(alias="to")]):
    """Range KPIs: appointments, no-show rate, revenue, collection rate,
    new patients, visits."""
    if from_date > to_date:
        raise AppError("VALIDATION", "from must be <= to")
    start = datetime.combine(from_date, time.min)
    end = datetime.combine(to_date, time.max)

    appointments = db.scalars(
        select(Appointment).where(
            Appointment.date >= from_date, Appointment.date <= to_date
        )
    ).all()
    total_appts = len(appointments)
    completed = sum(1 for a in appointments if a.status == "completed")
    cancelled = sum(1 for a in appointments if a.status == "cancelled")
    no_show = sum(1 for a in appointments if a.status == "no_show")
    active = sum(1 for a in appointments if a.status in ("booked", "checked_in", "in_progress"))
    denominator = total_appts - cancelled
    no_show_rate = round(no_show * 100 / denominator, 1) if denominator else 0.0

    payments = db.scalars(
        select(Payment).where(Payment.paid_at >= start, Payment.paid_at <= end)
    ).all()
    revenue = round(
        sum(float(p.amount) for p in payments if not p.is_refund)
        - sum(float(p.amount) for p in payments if p.is_refund),
        2,
    )
    refunds = round(sum(float(p.amount) for p in payments if p.is_refund), 2)

    invoices = db.scalars(
        select(Invoice).where(Invoice.issued_at >= start, Invoice.issued_at <= end)
    ).all()
    invoiced = round(sum(float(i.total) for i in invoices), 2)
    collected = round(
        sum(float(i.paid_total) - float(i.refunded_total) for i in invoices), 2
    )
    collection_rate = round(collected * 100 / invoiced, 1) if invoiced else 0.0

    new_patients = db.scalar(
        select(func.count()).select_from(PatientProfile).where(
            PatientProfile.created_at >= start, PatientProfile.created_at <= end
        )
    )
    visits = db.scalar(
        select(func.count()).select_from(Visit).where(
            Visit.started_at >= start, Visit.started_at <= end
        )
    )
    return {
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "appointments": {
            "total": total_appts,
            "completed": completed,
            "cancelled": cancelled,
            "no_show": no_show,
            "booked": active,
        },
        "no_show_rate": no_show_rate,
        "revenue": revenue,
        "refunds": refunds,
        "invoiced": invoiced,
        "collection_rate": collection_rate,
        "new_patients": new_patients or 0,
        "visits": visits or 0,
    }
