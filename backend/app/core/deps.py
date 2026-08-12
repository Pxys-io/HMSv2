"""FastAPI dependencies: auth, role guards, CSRF, audit correlation."""

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_audit_db, get_db
from app.models.identity import PatientAccount, StaffUser

DbDep = Annotated[Session, Depends(get_db)]
AuditDbDep = Annotated[Session, Depends(get_audit_db)]


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", uuid.uuid4().hex)


def get_current_staff(request: Request, db: DbDep) -> StaffUser:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise AppError("UNAUTHORIZED", "missing bearer token")
    try:
        claims = decode_access_token(auth[7:])
    except jwt.PyJWTError:
        raise AppError("UNAUTHORIZED", "invalid or expired token") from None
    if claims.get("typ") != "staff":
        raise AppError("UNAUTHORIZED", "wrong token type")
    user = db.get(StaffUser, int(claims["sub"]))
    if user is None or not user.is_active:
        raise AppError("UNAUTHORIZED", "user not found or inactive")
    return user


def get_current_patient(request: Request, db: DbDep) -> PatientAccount:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise AppError("UNAUTHORIZED", "missing bearer token")
    try:
        claims = decode_access_token(auth[7:])
    except jwt.PyJWTError:
        raise AppError("UNAUTHORIZED", "invalid or expired token") from None
    if claims.get("typ") != "patient":
        raise AppError("UNAUTHORIZED", "wrong token type")
    account = db.get(PatientAccount, int(claims["sub"]))
    if account is None or not account.is_active:
        raise AppError("UNAUTHORIZED", "account not found or inactive")
    return account


def require_role(*roles: str):
    """System-role guard (admin/doctor/secretary by name). Custom roles get
    'custom' from the `role` property and are handled by require_perm."""

    def checker(staff: Annotated[StaffUser, Depends(get_current_staff)]) -> StaffUser:
        if staff.role not in roles:
            raise AppError("FORBIDDEN", "insufficient role")
        return staff

    return checker


def require_any_perm(*codes: str):
    """Passes when the user holds ANY of the given permissions."""

    def checker(staff: Annotated[StaffUser, Depends(get_current_staff)]) -> StaffUser:
        allowed = staff.permission_codes
        if not any(c in allowed for c in codes):
            raise AppError("FORBIDDEN", "insufficient permission")
        return staff

    return checker


def require_perm(*codes: str):
    """Permission guard (Plan/14 A1): the user's role must hold ALL codes.
    Admins implicitly pass (system role with every permission)."""

    def checker(staff: Annotated[StaffUser, Depends(get_current_staff)]) -> StaffUser:
        allowed = staff.permission_codes
        missing = [c for c in codes if c not in allowed]
        if missing:
            raise AppError("FORBIDDEN", f"missing permission(s): {', '.join(missing)}")
        return staff

    return checker


def verify_csrf(request: Request) -> None:
    """Double-submit check for cookie-authenticated mutations.

    Mutations authenticated via the refresh cookie (or the guest chat cookie)
    must echo the CSRF token in `X-CSRF-Token`. Bearer-token requests are
    exempt because the token is not sent automatically by the browser.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if request.headers.get("Authorization", "").startswith("Bearer "):
        return  # bearer-authenticated; CSRF is not the defense here
    settings = get_settings()
    cookie = request.cookies.get(settings.CSRF_COOKIE_NAME)
    if cookie is None:
        return  # no CSRF cookie -> not cookie-authenticated
    header = request.headers.get("X-CSRF-Token")
    if not header or header != cookie:
        raise AppError("FORBIDDEN", "CSRF token mismatch")
