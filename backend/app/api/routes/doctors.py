"""Admin doctor management (Plan/02 §3 admin management, Plan/04 display token)."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_role
from app.core.errors import AppError
from app.core.pagination import paginate
from app.core.security import hash_password, sha256_hex
from app.models.config import Setting
from app.models.identity import Doctor, StaffUser
from app.schemas.auth import DoctorCreate, DoctorUpdate

router = APIRouter(prefix="/api/doctors", tags=["doctors"])
admin = Annotated[StaffUser, Depends(require_role("admin"))]


@router.get("")
def list_doctors(current: admin, db: DbDep, page: int = Query(1, ge=1), page_size: int = Query(20,
    ge=1, le=100)):
    stmt = select(Doctor).order_by(Doctor.id)
    result = paginate(db, stmt, page, page_size)
    result["items"] = [_payload(d) for d in result["items"]]
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
    user = StaffUser(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        full_name_ar=body.full_name_ar,
        phone=body.phone,
        role="doctor",
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
    db.add(doctor)
    db.flush()  # assign ids before the audited commit
    with audit.audited_action(
        audit_db,
        actor_type="staff",
        actor_id=current.id,
        actor_label=current.email,
        action="doctor.create",
        correlation_id=get_request_id(request),
        entity_type="doctor",
        entity_id=str(doctor.id),
        after=_payload(doctor),
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return _payload(doctor)


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
    before = _payload(doctor)
    for field in body.model_fields_set:
        setattr(doctor, field, getattr(body, field))
    with audit.audited_action(
        audit_db,
        actor_type="staff",
        actor_id=current.id,
        actor_label=current.email,
        action="doctor.update",
        correlation_id=get_request_id(request),
        entity_type="doctor",
        entity_id=str(doctor.id),
        before=before,
        after=_payload(doctor),
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return _payload(doctor)


def _payload(doctor: Doctor) -> dict:
    return {
        "id": doctor.id,
        "staff_user_id": doctor.staff_user_id,
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
    }


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
