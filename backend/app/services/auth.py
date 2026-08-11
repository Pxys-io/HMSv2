"""Shared auth helpers for staff and public auth routers."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.config import get_settings
from app.core.cookies import clear_auth_cookies, set_auth_cookies
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    refresh_expiry,
    sha256_hex,
    verify_password,
)
from app.core.timeutil import ensure_aware
from app.models.identity import RefreshToken

_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
_MAX_FAILS = 10
_WINDOW_SECONDS = 600


def check_login_lockout(identifier: str) -> None:
    now = datetime.now(UTC).timestamp()
    recent = [t for t in _LOGIN_ATTEMPTS.get(identifier, []) if now - t < _WINDOW_SECONDS]
    _LOGIN_ATTEMPTS[identifier] = recent
    if len(recent) >= _MAX_FAILS:
        raise AppError("RATE_LIMITED", "too many failed attempts, try again in 10 minutes")


def record_failed_login(identifier: str) -> None:
    _LOGIN_ATTEMPTS.setdefault(identifier, []).append(datetime.now(UTC).timestamp())


def clear_login_lockout(identifier: str) -> None:
    _LOGIN_ATTEMPTS.pop(identifier, None)


def issue_tokens(
    response: Response,
    *,
    owner_type: Literal["staff", "patient"],
    owner_id: int,
    role: str | None,
    name: str | None,
    db: Session,
    ip: str | None,
) -> dict:
    """Creates a refresh token row, sets cookies, returns the access token."""
    raw, token_hash, family = generate_refresh_token()
    db.add(
        RefreshToken(
            owner_type=owner_type,
            owner_id=owner_id,
            token_hash=token_hash,
            family_id=family,
            expires_at=refresh_expiry(owner_type),
            created_by_ip=ip,
        )
    )
    db.commit()
    set_auth_cookies(response, raw)
    return {
        "access_token": create_access_token(
            subject=str(owner_id), token_type=owner_type, role=role, name=name
        ),
        "owner_id": owner_id,
        "role": role,
        "name": name,
    }


def rotate_refresh(
    response: Response,
    request: Request,
    db: Session,
    *,
    owner_type: Literal["staff", "patient"],
    role: str | None,
    name: str | None,
) -> dict:
    """Validates the refresh cookie, rotates the token, returns new access."""
    settings = get_settings()
    raw = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not raw:
        raise AppError("UNAUTHORIZED", "missing refresh token")
    token_hash = sha256_hex(raw)
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    now = datetime.now(UTC)
    if row is None:
        raise AppError("UNAUTHORIZED", "unknown refresh token")

    if row.revoked_at is not None:
        # Reuse of a rotated token = suspected theft: kill the whole family.
        family = db.scalars(
            select(RefreshToken).where(RefreshToken.family_id == row.family_id)
        ).all()
        for tok in family:
            tok.revoked_at = now
        db.commit()
        clear_auth_cookies(response)
        raise AppError("UNAUTHORIZED", "refresh token reused; session revoked")

    if row.owner_type != owner_type or ensure_aware(row.expires_at) < now:
        raise AppError("UNAUTHORIZED", "refresh token expired or wrong type")

    row.revoked_at = now
    raw_new, token_hash_new, _ = generate_refresh_token()
    db.add(
        RefreshToken(
            owner_type=owner_type,
            owner_id=row.owner_id,
            token_hash=token_hash_new,
            family_id=row.family_id,
            expires_at=refresh_expiry(owner_type),
            created_by_ip=request.client.host if request.client else None,
        )
    )
    db.commit()
    set_auth_cookies(response, raw_new)
    return {
        "access_token": create_access_token(
            subject=str(row.owner_id), token_type=owner_type, role=role, name=name
        ),
        "owner_id": row.owner_id,
        "role": role,
        "name": name,
    }


def revoke_session(request: Request, response: Response, db: Session) -> None:
    settings = get_settings()
    raw = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if raw:
        row = db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == sha256_hex(raw))
        )
        if row:
            family = db.scalars(
                select(RefreshToken).where(RefreshToken.family_id == row.family_id)
            ).all()
            for tok in family:
                tok.revoked_at = datetime.now(UTC)
            db.commit()
    clear_auth_cookies(response)


def verify_credentials(password: str, password_hash: str, identifier: str) -> None:
    if not verify_password(password, password_hash):
        record_failed_login(identifier)
        raise AppError("UNAUTHORIZED", "invalid credentials")


def audit_login(
    audit_db: Session,
    *,
    success: bool,
    identifier: str,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    correlation_id: str,
    ip: str | None,
) -> None:
    audit.access(
        audit_db,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action="auth.login" if success else "auth.login_failed",
        entity_type="identity",
        entity_id=str(actor_id) if actor_id else identifier,
        correlation_id=correlation_id,
        ip=ip,
    )
