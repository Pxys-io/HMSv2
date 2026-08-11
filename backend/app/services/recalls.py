"""Recall service (Plan/07 R1–R2): follow-up-due patients without a future
appointment, plus no-show surfacing."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.emr import Visit
from app.models.identity import Doctor, PatientProfile, StaffUser
from app.models.scheduling import Appointment
from app.services.settings import get_setting


def recall_list(db: Session, lookahead_days: int | None = None) -> list[dict]:
    lookahead = lookahead_days or int(get_setting(db, "booking.recall_lookahead_days", 7))
    today = date.today()
    due = today + timedelta(days=lookahead)

    visits = db.scalars(
        select(Visit).where(
            Visit.follow_up_due.isnot(None),
            Visit.follow_up_due <= due,
            (Visit.recall_dismissed_until.is_(None)) | (Visit.recall_dismissed_until < today),
        ).order_by(Visit.follow_up_due)
    ).all()

    rows = []
    for visit in visits:
        profile = db.get(PatientProfile, visit.patient_profile_id)
        if profile is None:
            continue
        has_future = db.scalar(
            select(Appointment.id).where(
                Appointment.patient_profile_id == profile.id,
                Appointment.date >= today,
                Appointment.status.in_(("booked", "checked_in", "in_progress")),
            ).limit(1)
        )
        if has_future:
            continue
        doctor = db.get(Doctor, visit.doctor_id)
        doctor_name = None
        if doctor:
            user = db.get(StaffUser, doctor.staff_user_id)
            doctor_name = user.full_name if user else None
        days_until = (visit.follow_up_due - today).days
        rows.append(
            {
                "visit_id": visit.id,
                "patient_profile_id": profile.id,
                "patient_name": profile.full_name,
                "phone": profile.phone,
                "doctor_id": visit.doctor_id,
                "doctor_name": doctor_name,
                "follow_up_due": visit.follow_up_due.isoformat(),
                "days_overdue": -days_until if days_until < 0 else 0,
                "days_until_due": max(days_until, 0),
                "last_visit_summary": visit.chief_complaint or visit.plan or None,
                "no_show_count": profile.no_show_count,
            }
        )
    return rows


def dismiss(db: Session, visit_id: int, days: int) -> dict:
    visit = db.get(Visit, visit_id)
    if visit is None:
        raise AppError("NOT_FOUND", "visit not found")
    if days < 1 or days > 365:
        raise AppError("VALIDATION", "days must be between 1 and 365")
    visit.recall_dismissed_until = date.today() + timedelta(days=days)
    db.commit()
    return {"visit_id": visit_id, "dismissed_until": visit.recall_dismissed_until.isoformat()}
