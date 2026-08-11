"""Admin user management (Plan/02 §3 admin management)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_role
from app.core.errors import AppError
from app.core.pagination import paginate
from app.core.security import hash_password
from app.models.identity import StaffUser
from app.schemas.auth import UserCreate, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])
admin = Annotated[StaffUser, Depends(require_role("admin"))]


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
    user = StaffUser(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        full_name_ar=body.full_name_ar,
        phone=body.phone,
        role=body.role,
        must_change_password=True,
    )
    db.add(user)
    db.flush()  # assign id before the audited commit
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
    if body.role is not None:
        user.role = body.role
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
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
    }
