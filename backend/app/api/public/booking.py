"""Public booking API (Plan/03 §3.2): bookable doctors, availability,
visit types, and patient booking/move/cancel. Calls only from the public
site; public-safe projections only (no phones, internal rates, or counts)."""

import json
from datetime import UTC, date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuditDbDep, DbDep, get_current_patient, get_request_id, verify_csrf
from app.core.errors import AppError
from app.models.identity import Doctor, PatientAccount, PatientProfile
from app.models.scheduling import Appointment, VisitType
from app.schemas.scheduling import AppointmentCancel, AppointmentMove, PublicAppointmentCreate
from app.services import appointments as appt_service
from app.services.availability import day_availability
from app.services.idempotency import claim, get_key_from_request
from app.services.settings import clinic_today

_csrf = Depends(verify_csrf)
router = APIRouter(prefix="/api/public", tags=["public-booking"], dependencies=[_csrf])
Patient = Annotated[PatientAccount, Depends(get_current_patient)]


def _doctor_payload(doctor: Doctor, full_name: str | None) -> dict:
    return {
        "id": doctor.id,
        "full_name": full_name or f"Doctor {doctor.id}",
        "specialty": doctor.specialty,
        "title": doctor.title,
        "bio": doctor.bio,
        "bio_ar": doctor.bio_ar,
        "booking_mode": doctor.booking_mode,
        "public_asset_id": doctor.public_asset_id,
    }


@router.get("/doctors")
def public_doctors(db: DbDep):
    from app.models.identity import StaffUser

    rows = db.execute(
        select(Doctor, StaffUser.full_name)
        .join(StaffUser, Doctor.staff_user_id == StaffUser.id)
        .where(Doctor.is_bookable_online.is_(True))
        .order_by(Doctor.id)
    ).all()
    return [_doctor_payload(d, name) for d, name in rows]


@router.get("/doctors/{doctor_id}/availability")
def public_availability(
    doctor_id: int,
    db: DbDep,
    from_date: Annotated[date, Query(alias="from")],
    to_date: Annotated[date, Query(alias="to")],
    visit_type_id: Annotated[int, Query()],
):
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise AppError("NOT_FOUND", "doctor not found")
    vt = db.get(VisitType, visit_type_id)
    if vt is None or not vt.is_active:
        raise AppError("NOT_FOUND", "visit type not found")
    if to_date < from_date or (to_date - from_date).days > 60:
        raise AppError("VALIDATION", "invalid date range")
    days = []
    cursor = from_date
    while cursor <= to_date:
        days.append(day_availability(db, doctor, cursor, vt, public=True))
        cursor += timedelta(days=1)
    return {"doctor_id": doctor_id, "visit_type_id": visit_type_id, "days": days}


@router.get("/visit-types")
def public_visit_types(db: DbDep, doctor_id: int = Query(...)):
    if db.get(Doctor, doctor_id) is None:
        raise AppError("NOT_FOUND", "doctor not found")
    rows = db.scalars(
        select(VisitType).where(VisitType.is_active.is_(True)).order_by(VisitType.id)
    ).all()
    return [
        {
            "id": v.id,
            "name": v.name,
            "name_ar": v.name_ar,
            "duration_minutes": v.duration_minutes,
            "default_price": float(v.default_price),
        }
        for v in rows
    ]


def _public_appointment_payload(appt: Appointment) -> dict:
    return {
        "id": appt.id,
        "booking_ref": appt.booking_ref,
        "doctor_id": appt.doctor_id,
        "visit_type_id": appt.visit_type_id,
        "profile_id": appt.patient_profile_id,
        "date": appt.date.isoformat(),
        "start_time": appt.start_time.strftime("%H:%M") if appt.start_time else None,
        "status": appt.status,
        "source": appt.source,
    }


def _after_public_booking(db: Session, appt: Appointment, account: PatientAccount) -> None:
    """N1/N3: fan out the in-app notification and enqueue the confirmation email."""
    from app.models.comms import OutboxEvent
    from app.models.identity import Doctor, StaffUser
    from app.services import notify

    doctor = db.get(Doctor, appt.doctor_id)
    doctor_name = None
    if doctor:
        user = db.get(StaffUser, doctor.staff_user_id)
        doctor_name = user.full_name if user else None
    title = "New booking"
    body = (
        f"{account.full_name} booked {appt.date.isoformat()} "
        f"at {appt.start_time} with {doctor_name}"
        if appt.start_time
        else f"{account.full_name} booked {appt.date.isoformat()} with {doctor_name}"
    )
    for notification in notify.fan_out(db, type="booking_new", title=title, body=body,
                                       roles=("admin", "secretary")):
        from app.api.routes.notifications import broadcast_notification

        broadcast_notification(
            notification.staff_user_id,
            {
                "type": "booking_new",
                "title": title,
                "body": body,
                "notification_id": notification.id,
            },
        )
    db.commit()

    if account.email:
        from datetime import datetime

        from app.services.emailer import render_confirmation

        subject, html = render_confirmation(
            clinic_name="Clinic",  # filled from settings at send time in v1
            patient_name=account.full_name,
            doctor_name=doctor_name or "",
            date_text=appt.date.isoformat(),
            time_text=appt.start_time.strftime("%H:%M") if appt.start_time else "",
            booking_ref=appt.booking_ref,
            locale=account.locale,
        )

        db.add(
            OutboxEvent(
                kind="email_booking_confirmation",
                aggregate_type="appointment",
                aggregate_id=appt.id,
                payload={"to": account.email, "subject": subject, "html": html},
                status="pending",
                next_attempt_at=datetime.now(UTC),
                dedupe_key=f"email:{appt.booking_ref}",
            )
        )
        from app.services.communications import log_communication

        log_communication(
            db,
            patient_profile_id=appt.patient_profile_id,
            channel="email",
            summary=f"Booking confirmation {appt.booking_ref} sent to {account.email}",
        )


def _own_profile(db: Session, account: PatientAccount, profile_id: int) -> PatientProfile:
    profile = db.get(PatientProfile, profile_id)
    if profile is None or profile.account_id != account.id:
        raise AppError("FORBIDDEN", "not your profile")
    return profile


@router.post("/appointments")
def public_book(
    body: PublicAppointmentCreate,
    current: Patient,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    key = get_key_from_request(request)
    if key:
        replay = claim(db, owner_type="patient", owner_id=current.id, key=key,
                       payload=body.model_dump(mode="json"))
        if replay:
            return Response(
                status_code=replay["status"],
                content=json.dumps(replay["body"], ensure_ascii=False),
                media_type="application/json",
            )
    profile = _own_profile(db, current, body.profile_id)
    appt = appt_service.book(
        db, audit_db,
        actor_type="patient", actor_id=current.id, actor_label=current.full_name,
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
        patient_profile_id=profile.id,
        doctor_id=body.doctor_id,
        visit_type_id=body.visit_type_id,
        target_date=body.date,
        start_time=body.start_time,
        source="public",
        idempotency_key=key,
    )
    _after_public_booking(db, appt, current)
    return _public_appointment_payload(appt)


@router.get("/appointments")
def public_list_appointments(current: Patient, db: DbDep):
    profile_ids = [
        p.id
        for p in db.scalars(
            select(PatientProfile).where(PatientProfile.account_id == current.id)
        ).all()
    ]
    if not profile_ids:
        return {"upcoming": [], "past": []}
    rows = db.scalars(
        select(Appointment)
        .where(Appointment.patient_profile_id.in_(profile_ids))
        .order_by(Appointment.date.desc(), Appointment.start_time.desc())
    ).all()
    today = clinic_today()
    upcoming = [
        _public_appointment_payload(a)
        for a in rows
        if a.status not in ("cancelled", "no_show") and a.date >= today
    ]
    past = [
        _public_appointment_payload(a)
        for a in rows
        if a.status in ("cancelled", "no_show") or a.date < today
    ]
    return {"upcoming": upcoming, "past": past}


@router.post("/appointments/{appointment_id}/cancel")
def public_cancel(
    appointment_id: int,
    body: AppointmentCancel,
    current: Patient,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    appt = db.get(Appointment, appointment_id)
    if appt is None:
        raise AppError("NOT_FOUND", "appointment not found")
    _own_profile(db, current, appt.patient_profile_id)
    cancelled = appt_service.cancel(
        db, audit_db, appt=appt,
        actor_type="patient", actor_id=current.id, actor_label=current.full_name,
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
        reason=body.reason,
    )
    return _public_appointment_payload(cancelled)


@router.post("/appointments/{appointment_id}/move")
def public_move(
    appointment_id: int,
    body: AppointmentMove,
    current: Patient,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    appt = db.get(Appointment, appointment_id)
    if appt is None:
        raise AppError("NOT_FOUND", "appointment not found")
    _own_profile(db, current, appt.patient_profile_id)
    moved = appt_service.move(
        db, audit_db, appt=appt,
        actor_type="patient", actor_id=current.id, actor_label=current.full_name,
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
        new_date=body.date, new_start=body.start_time,
    )
    return _public_appointment_payload(moved)
