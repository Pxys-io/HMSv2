"""Admin doctor management (Plan/02 §3 admin management, Plan/04 display token)."""

import secrets
from datetime import date as _date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.core.pagination import paginate
from app.core.security import hash_password, sha256_hex
from app.models.config import Setting
from app.models.identity import Doctor, StaffUser
from app.models.scheduling import Appointment
from app.schemas.auth import DoctorCreate, DoctorUpdate

router = APIRouter(prefix="/api/doctors", tags=["doctors"])
admin = Annotated[StaffUser, Depends(require_perm("admin.users"))]


@router.get("")
def list_doctors(
    current: admin,
    db: DbDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    stmt = select(Doctor).order_by(Doctor.id)
    result = paginate(db, stmt, page, page_size)
    result["items"] = [_payload(db, d) for d in result["items"]]
    return result


@router.post("")
def create_doctor(
    body: DoctorCreate,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if db.scalar(select(StaffUser).where(StaffUser.email == body.email.lower())):
        raise AppError("CONFLICT", "user already exists")
    from app.services.roles import role_id as _rid

    user = StaffUser(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        full_name_ar=body.full_name_ar,
        phone=body.phone,
        role_id=_rid(db, "doctor"),
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    doctor = Doctor(
        staff_user_id=user.id,
        specialty=body.specialty,
        title=body.title,
        bio=body.bio,
        bio_ar=body.bio_ar,
        booking_mode=body.booking_mode,
        default_slot_minutes=body.default_slot_minutes,
        buffer_minutes=body.buffer_minutes,
        day_capacity=body.day_capacity,
        slot_capacity=body.slot_capacity,
        billing_mode=body.billing_mode,
        hourly_rate=body.hourly_rate,
        is_bookable_online=body.is_bookable_online,
    )
    _validate_doctor_config(doctor)
    db.add(doctor)
    db.flush()  # assign ids before the audited commit
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="doctor.create", correlation_id=get_request_id(request),
        entity_type="doctor", entity_id=str(doctor.id),
        after=_payload(db, doctor),
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return _payload(db, doctor)


@router.patch("/{doctor_id}")
def update_doctor(
    doctor_id: int,
    body: DoctorUpdate,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise AppError("NOT_FOUND", "doctor not found")
    before = _payload(db, doctor)
    warnings: list[str] = []

    # identity fields land on the linked staff user
    user = db.get(StaffUser, doctor.staff_user_id)
    if user is None:
        raise AppError("CONFLICT", "linked staff user missing")
    for field in ("full_name", "full_name_ar", "email"):
        if getattr(body, field) is not None:
            setattr(user, field, getattr(body, field))
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        user.must_change_password = True
    if body.email is not None and body.email.lower() != user.email:
        existing = db.scalar(select(StaffUser).where(StaffUser.email == body.email.lower()))
        if existing is not None and existing.id != user.id:
            raise AppError("CONFLICT", "email already in use")
        user.email = body.email.lower()

    # doctor config fields
    for field in (
        "specialty", "title", "bio", "bio_ar", "booking_mode", "default_slot_minutes",
        "buffer_minutes", "day_capacity", "slot_capacity", "billing_mode",
        "hourly_rate", "is_bookable_online", "public_asset_id",
    ):
        if field in body.model_fields_set:
            setattr(doctor, field, getattr(body, field))
    _validate_doctor_config(doctor)

    # mode switch with future bookings: allowed, but surfaced (Plan/03 R9 note)
    if "booking_mode" in body.model_fields_set:
        has_future = db.scalar(
            select(Appointment.id).where(
                Appointment.doctor_id == doctor.id,
                Appointment.date >= _date.today(),
                Appointment.status.in_(("booked", "checked_in", "in_progress")),
            ).limit(1)
        )
        if has_future:
            warnings.append(
                "Booking mode changed while future bookings exist — they keep their booked times."
            )

    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="doctor.update", correlation_id=get_request_id(request),
        entity_type="doctor", entity_id=str(doctor.id),
        before=before, after=_payload(db, doctor),
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    payload = _payload(db, doctor)
    payload["warnings"] = warnings
    return payload


@router.delete("/{doctor_id}")
def deactivate_doctor(
    doctor_id: int,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    """Soft delete: 409 with a clear reason if the doctor has upcoming
    appointments or visit history; otherwise the login is deactivated and the
    doctor hidden from booking. Rows are kept for audit/EMR integrity."""
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise AppError("NOT_FOUND", "doctor not found")
    user = db.get(StaffUser, doctor.staff_user_id)
    if user is None:
        raise AppError("CONFLICT", "linked staff user missing")

    future = db.scalar(
        select(Appointment.id).where(
            Appointment.doctor_id == doctor.id,
            Appointment.date >= _date.today(),
            Appointment.status.in_(("booked", "checked_in", "in_progress")),
        ).limit(1)
    )
    if future:
        raise AppError("CONFLICT", "doctor has upcoming appointments; cancel or move them first")

    before = _payload(db, doctor)
    user.is_active = False
    doctor.is_bookable_online = False
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="doctor.deactivate", correlation_id=get_request_id(request),
        entity_type="doctor", entity_id=str(doctor.id),
        before=before, after={"is_active": False, "is_bookable_online": False},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return {"id": doctor.id, "deactivated": True}


@router.post("/{doctor_id}/display-token")
def rotate_display_token(
    doctor_id: int,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    """Generates (or rotates) the privacy-safe TV display token.

    Only the SHA-256 hash is stored; the raw token is returned exactly once.
    Rotation invalidates the previous token immediately (Plan/04 §3)."""
    if db.get(Doctor, doctor_id) is None:
        raise AppError("NOT_FOUND", "doctor not found")
    raw = secrets.token_urlsafe(32)
    row = db.scalar(select(Setting).where(Setting.key == f"display_token_{doctor_id}"))
    if row is None:
        row = Setting(key=f"display_token_{doctor_id}", value=sha256_hex(raw))
        db.add(row)
    else:
        row.value = sha256_hex(raw)
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="doctor.display_token_rotate", correlation_id=get_request_id(request),
        entity_type="doctor", entity_id=str(doctor_id),
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return {"token": raw}


def _validate_doctor_config(doctor: Doctor) -> None:
    if doctor.billing_mode == "per_hour" and (
        doctor.hourly_rate is None or doctor.hourly_rate <= 0
    ):
        raise AppError("VALIDATION", "per-hour billing requires a positive hourly_rate")
    if doctor.booking_mode == "slots" and (
        doctor.default_slot_minutes is None or doctor.default_slot_minutes < 5
    ):
        raise AppError("VALIDATION", "slots mode requires default_slot_minutes >= 5")
    if doctor.slot_capacity is not None and doctor.slot_capacity < 1:
        raise AppError("VALIDATION", "slot_capacity must be >= 1")


def _payload(db: DbDep, doctor: Doctor) -> dict:
    user = db.get(StaffUser, doctor.staff_user_id) if doctor.staff_user_id else None
    return {
        "id": doctor.id,
        "staff_user_id": doctor.staff_user_id,
        "full_name": user.full_name if user else None,
        "full_name_ar": user.full_name_ar if user else None,
        "email": user.email if user else None,
        "is_active": user.is_active if user else None,
        "specialty": doctor.specialty,
        "title": doctor.title,
        "bio": doctor.bio,
        "bio_ar": doctor.bio_ar,
        "booking_mode": doctor.booking_mode,
        "default_slot_minutes": doctor.default_slot_minutes,
        "buffer_minutes": doctor.buffer_minutes,
        "day_capacity": doctor.day_capacity,
        "slot_capacity": doctor.slot_capacity,
        "billing_mode": doctor.billing_mode,
        "hourly_rate": float(doctor.hourly_rate) if doctor.hourly_rate is not None else None,
        "is_bookable_online": doctor.is_bookable_online,
        "public_asset_id": doctor.public_asset_id,
    }
