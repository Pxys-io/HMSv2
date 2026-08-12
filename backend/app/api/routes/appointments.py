"""Staff appointment routes (Plan/03 §3.1): calendar feed, booking (with
force), move, cancel, no-show."""

import json
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.core.pagination import paginate
from app.models.identity import PatientProfile, StaffUser
from app.models.scheduling import Appointment
from app.schemas.scheduling import AppointmentCancel, AppointmentCreate, AppointmentMove
from app.services import appointments as appt_service
from app.services.idempotency import claim, get_key_from_request

router = APIRouter(prefix="/api/appointments", tags=["appointments"])
staff = Annotated[StaffUser, Depends(require_perm("appointment.view"))]


def _payload(appt: Appointment, db: Session) -> dict:
    profile = db.get(PatientProfile, appt.patient_profile_id)
    return {
        "id": appt.id,
        "booking_ref": appt.booking_ref,
        "patient_profile_id": appt.patient_profile_id,
        "patient_name": profile.full_name if profile else None,
        "patient_phone": profile.phone if profile else None,
        "doctor_id": appt.doctor_id,
        "visit_type_id": appt.visit_type_id,
        "date": appt.date.isoformat(),
        "start_time": appt.start_time.strftime("%H:%M") if appt.start_time else None,
        "end_time": appt.end_time.strftime("%H:%M") if appt.end_time else None,
        "status": appt.status,
        "source": appt.source,
        "follow_up_of_id": appt.follow_up_of_id,
        "cancel_reason": appt.cancel_reason,
        "cancelled_by": appt.cancelled_by,
        "reminder_link_generated_at": appt.reminder_link_generated_at.isoformat()
        if appt.reminder_link_generated_at
        else None,
    }


@router.get("")
def list_appointments(
    current: Annotated[StaffUser, Depends(require_perm("appointment.view"))],
    db: DbDep,
    doctor_id: int | None = None,
    date: date | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    stmt = select(Appointment).order_by(Appointment.date, Appointment.start_time)
    if doctor_id is not None:
        stmt = stmt.where(Appointment.doctor_id == doctor_id)
    if date is not None:
        stmt = stmt.where(Appointment.date == date)
    if status is not None:
        stmt = stmt.where(Appointment.status == status)
    result = paginate(db, stmt, page, page_size)
    result["items"] = [_payload(a, db) for a in result["items"]]
    return result


@router.post("")
def staff_book(
    body: AppointmentCreate,
    current: Annotated[StaffUser, Depends(require_perm("appointment.view"))],
    request: Request,
    response: Response,
    db: DbDep,
    audit_db: AuditDbDep,
):
    key = get_key_from_request(request)
    if key:
        replay = claim(db, owner_type="staff", owner_id=current.id, key=key,
                       payload=body.model_dump(mode="json"))
        if replay:
            return Response(
                status_code=replay["status"],
                content=json.dumps(replay["body"], ensure_ascii=False),
                media_type="application/json",
            )
    appt = appt_service.book(
        db, audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
        patient_profile_id=body.patient_profile_id,
        doctor_id=body.doctor_id,
        visit_type_id=body.visit_type_id,
        target_date=body.date,
        start_time=body.start_time,
        source="staff",
        force=body.force,
        follow_up_of_id=body.follow_up_of_id,
        idempotency_key=key,
    )
    return _payload(appt, db)


@router.get("/{appointment_id}")
def get_appointment(
    appointment_id: int,
    current: Annotated[StaffUser, Depends(require_perm("appointment.view"))],
    db: DbDep,
):
    appt = db.get(Appointment, appointment_id)
    if appt is None:
        raise AppError("NOT_FOUND", "appointment not found")
    return _payload(appt, db)


@router.post("/{appointment_id}/move")
def move_appointment(
    appointment_id: int,
    body: AppointmentMove,
    current: Annotated[StaffUser, Depends(require_perm("appointment.view"))],
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    appt = db.get(Appointment, appointment_id)
    if appt is None:
        raise AppError("NOT_FOUND", "appointment not found")
    moved = appt_service.move(
        db, audit_db, appt=appt,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
        new_date=body.date, new_start=body.start_time,
    )
    return _payload(moved, db)


@router.post("/{appointment_id}/cancel")
def cancel_appointment(
    appointment_id: int,
    body: AppointmentCancel,
    current: Annotated[StaffUser, Depends(require_perm("appointment.view"))],
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    appt = db.get(Appointment, appointment_id)
    if appt is None:
        raise AppError("NOT_FOUND", "appointment not found")
    cancelled = appt_service.cancel(
        db, audit_db, appt=appt,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
        reason=body.reason,
    )
    return _payload(cancelled, db)


@router.post("/{appointment_id}/no-show")
def no_show_appointment(
    appointment_id: int,
    current: Annotated[StaffUser, Depends(require_perm("appointment.view"))],
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    appt = db.get(Appointment, appointment_id)
    if appt is None:
        raise AppError("NOT_FOUND", "appointment not found")
    updated = appt_service.mark_no_show(
        db, audit_db, appt=appt,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    return _payload(updated, db)
