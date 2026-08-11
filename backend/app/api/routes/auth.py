"""Staff auth endpoints: login, refresh, logout, me (Plan/02 §3)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select

from app.core.deps import AuditDbDep, DbDep, get_current_staff, get_request_id, verify_csrf
from app.core.errors import AppError
from app.models.identity import StaffUser
from app.schemas.auth import StaffLoginRequest, TokenResponse
from app.services import auth as auth_service

_csrf = Depends(verify_csrf)
router = APIRouter(prefix="/api/auth", tags=["auth"], dependencies=[_csrf])


@router.post("/login", response_model=TokenResponse)
def staff_login(
    body: StaffLoginRequest, request: Request, response: Response, db: DbDep, audit_db: AuditDbDep
):
    identifier = body.email.lower()
    auth_service.check_login_lockout(identifier)
    user = db.scalar(select(StaffUser).where(StaffUser.email == identifier))
    if user is None or not user.is_active:
        auth_service.record_failed_login(identifier)
        raise AppError("UNAUTHORIZED", "invalid credentials")
    auth_service.verify_credentials(body.password, user.password_hash, identifier)
    auth_service.clear_login_lockout(identifier)

    user.last_login_at = datetime.now(UTC)
    db.commit()

    tokens = auth_service.issue_tokens(
        response,
        owner_type="staff",
        owner_id=user.id,
        role=user.role,
        name=user.full_name,
        db=db,
        ip=request.client.host if request.client else None,
    )
    auth_service.audit_login(
        audit_db,
        success=True,
        identifier=identifier,
        actor_type="staff",
        actor_id=user.id,
        actor_label=user.email,
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    return TokenResponse(access_token=tokens["access_token"], user=_user_payload(user))


@router.post("/refresh", response_model=TokenResponse)
def staff_refresh(request: Request, response: Response, db: DbDep):
    tokens = auth_service.rotate_refresh(
        response, request, db, owner_type="staff", role=None, name=None
    )
    user = db.get(StaffUser, tokens["owner_id"])
    if user is None or not user.is_active:
        raise AppError("UNAUTHORIZED", "user not found or inactive")
    return TokenResponse(access_token=tokens["access_token"], user=_user_payload(user))


@router.post("/logout", status_code=204)
def staff_logout(request: Request, response: Response, db: DbDep):
    auth_service.revoke_session(request, response, db)


@router.get("/me")
def staff_me(staff: Annotated[StaffUser, Depends(get_current_staff)]):
    return _user_payload(staff)


def _user_payload(user: StaffUser) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "full_name_ar": user.full_name_ar,
        "phone": user.phone,
        "role": user.role,
        "must_change_password": user.must_change_password,
    }
