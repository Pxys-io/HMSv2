"""Admin user management (Plan/02 §3 admin management)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.core.pagination import paginate
from app.core.security import hash_password
from app.models.identity import Doctor, Role, StaffUser
from app.models.scheduling import Appointment, DoctorSchedule
from app.schemas.auth import UserCreate, UserUpdate


def _resolve_role(db, body) -> Role:
    """role_id takes precedence; legacy `role` name is resolved via the
    role table (system names still work)."""
    if body.role_id is not None:
        role = db.get(Role, body.role_id)
        if role is None or not role.is_active:
            raise AppError("NOT_FOUND", "role not found")
        return role
    name = body.role or "secretary"
    role = db.scalar(select(Role).where(Role.name == name, Role.is_active.is_(True)))
    if role is None:
        raise AppError("NOT_FOUND", f"role '{name}' not found")
    return role

router = APIRouter(prefix="/api/users", tags=["users"])
admin = Annotated[StaffUser, Depends(require_perm("admin.users"))]


@router.get("")
def list_users(
    current: admin,
    db: DbDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    stmt = select(StaffUser).order_by(StaffUser.id)
    result = paginate(db, stmt, page, page_size)
    result["items"] = [_payload(u) for u in result["items"]]
    return result


@router.post("")
def create_user(
    body: UserCreate,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if db.scalar(select(StaffUser).where(StaffUser.email == body.email.lower())):
        raise AppError("CONFLICT", "user already exists")
    role = _resolve_role(db, body)
    user = StaffUser(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        full_name_ar=body.full_name_ar,
        phone=body.phone,
        role_id=role.id,
        must_change_password=True,
    )
    db.add(user)
    db.flush()  # assign id before the audited commit
    if role.name == "doctor":
        # doctor role implies a Doctor profile (Plan/02 §3) — auto-create it
        db.add(Doctor(staff_user_id=user.id, specialty="General"))
    with audit.audited_action(
        audit_db,
        actor_type="staff",
        actor_id=current.id,
        actor_label=current.email,
        action="user.create",
        correlation_id=get_request_id(request),
        entity_type="staff_user",
        entity_id=str(user.id),
        after={"role": user.role, "email": user.email},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return _payload(user)


@router.patch("/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdate,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    user = db.get(StaffUser, user_id)
    if user is None:
        raise AppError("NOT_FOUND", "user not found")
    before = _payload(user)
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.full_name_ar is not None:
        user.full_name_ar = body.full_name_ar
    if body.phone is not None:
        user.phone = body.phone
    if (body.role_id is not None or body.role is not None) and (
        body.role_id != user.role_id or (body.role_id is None and body.role != user.role)
    ):
        new_role = _resolve_role(db, body)
        if new_role.id != user.role_id:
            if new_role.name == "doctor":
                existing = db.scalar(select(Doctor).where(Doctor.staff_user_id == user.id))
                if existing is None:
                    db.add(Doctor(staff_user_id=user.id, specialty="General"))
                    db.flush()
            elif user.role == "doctor":
                doctor = db.scalar(select(Doctor).where(Doctor.staff_user_id == user.id))
                if doctor is not None:
                    in_use = db.scalar(
                        select(Appointment.id).where(
                            Appointment.doctor_id == doctor.id,
                            Appointment.status.in_(("booked", "checked_in", "in_progress")),
                        ).limit(1)
                    ) or db.scalar(
                        select(DoctorSchedule.id)
                        .where(DoctorSchedule.doctor_id == doctor.id)
                        .limit(1)
                    )
                    if in_use:
                        raise AppError(
                            "CONFLICT",
                            "doctor has schedules or active appointments; "
                            "deactivate via the Doctors tab first",
                        )
            user.role_id = new_role.id
            db.expire(user, ["role_obj"])
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        user.must_change_password = True
    with audit.audited_action(
        audit_db,
        actor_type="staff",
        actor_id=current.id,
        actor_label=current.email,
        action="user.update",
        correlation_id=get_request_id(request),
        entity_type="staff_user",
        entity_id=str(user.id),
        before=before,
        after=_payload(user),
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return _payload(user)


def _payload(user: StaffUser) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "full_name_ar": user.full_name_ar,
        "phone": user.phone,
        "role": user.role,
        "role_id": user.role_id,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
    }
