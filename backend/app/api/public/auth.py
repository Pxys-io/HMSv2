"""Public patient auth: register, login, refresh, logout, me (Plan/02 §3)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import or_, select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_current_patient, get_request_id, verify_csrf
from app.core.errors import AppError
from app.core.security import hash_password
from app.models.identity import PatientAccount
from app.schemas.auth import PatientLoginRequest, PatientRegisterRequest, TokenResponse
from app.services import auth as auth_service
from app.services.idempotency import claim, complete, get_key_from_request

_csrf = Depends(verify_csrf)
router = APIRouter(
    prefix="/api/public/auth", tags=["public-auth"], dependencies=[_csrf]
)


@router.post("/register", response_model=TokenResponse)
def patient_register(
    body: PatientRegisterRequest,
    request: Request,
    response: Response,
    db: DbDep,
    audit_db: AuditDbDep,
):
    key = get_key_from_request(request)
    if key:
        replay = claim(db, owner_type="patient", owner_id=None, key=key, payload=body.model_dump())
        if replay:
            return TokenResponse(**replay["body"])
    if not body.email and not body.phone:
        raise AppError("VALIDATION", "email or phone is required")
    exists = db.scalar(
        select(PatientAccount).where(
            or_(
                PatientAccount.email == (body.email or "").lower(),
                PatientAccount.phone == (body.phone or ""),
            )
        )
    )
    if exists:
        raise AppError("CONFLICT", "account already exists")

    account = PatientAccount(
        email=body.email.lower() if body.email else None,
        phone=body.phone,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(account)
    db.flush()
    from app.models.identity import PatientProfile
    from app.services.sequences import next_patient_code

    db.add(
        PatientProfile(
            code=next_patient_code(db),
            account_id=account.id,
            full_name=body.full_name,
            phone=body.phone or "",
        )
    )
    db.commit()

    tokens = auth_service.issue_tokens(
        response,
        owner_type="patient",
        owner_id=account.id,
        role=None,
        name=account.full_name,
        db=db,
        ip=request.client.host if request.client else None,
    )
    audit.access(
        audit_db,
        actor_type="patient",
        actor_id=account.id,
        actor_label=account.full_name,
        action="auth.register",
        entity_type="patient_account",
        entity_id=str(account.id),
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    if key:
        complete(
            db,
            owner_type="patient",
            owner_id=None,
            key=key,
            status=200,
            body=_tokens_body(tokens, account),
        )
    return TokenResponse(access_token=tokens["access_token"], user=_account_payload(account))


@router.post("/login", response_model=TokenResponse)
def patient_login(body: PatientLoginRequest, request: Request, response: Response, db: DbDep):
    identifier = body.email_or_phone.strip().lower()
    auth_service.check_login_lockout(identifier)
    account = db.scalar(
        select(PatientAccount).where(
            or_(
                PatientAccount.email == identifier,
                PatientAccount.phone == body.email_or_phone.strip(),
            )
        )
    )
    if account is None:
        auth_service.record_failed_login(identifier)
        raise AppError("UNAUTHORIZED", "invalid credentials")
    auth_service.verify_credentials(body.password, account.password_hash, identifier)
    auth_service.clear_login_lockout(identifier)
    account.last_login_at = datetime.now(UTC)
    db.commit()

    tokens = auth_service.issue_tokens(
        response,
        owner_type="patient",
        owner_id=account.id,
        role=None,
        name=account.full_name,
        db=db,
        ip=request.client.host if request.client else None,
    )
    return TokenResponse(access_token=tokens["access_token"], user=_account_payload(account))


@router.post("/refresh", response_model=TokenResponse)
def patient_refresh(request: Request, response: Response, db: DbDep):
    tokens = auth_service.rotate_refresh(response, request, db, owner_type="patient", role=None,
        name=None)
    account = db.get(PatientAccount, tokens["owner_id"])
    if account is None or not account.is_active:
        raise AppError("UNAUTHORIZED", "account not found or inactive")
    return TokenResponse(access_token=tokens["access_token"], user=_account_payload(account))


@router.post("/logout", status_code=204)
def patient_logout(request: Request, response: Response, db: DbDep):
    auth_service.revoke_session(request, response, db)


@router.get("/me")
def patient_me(account: Annotated[PatientAccount, Depends(get_current_patient)]):
    return _account_payload(account)


def _account_payload(account: PatientAccount) -> dict:
    return {
        "id": account.id,
        "full_name": account.full_name,
        "email": account.email,
        "phone": account.phone,
        "locale": account.locale,
        "email_verified": account.email_verified_at is not None,
        "phone_verified": account.phone_verified_at is not None,
    }


def _tokens_body(tokens: dict, account: PatientAccount) -> dict:
    return {
        "access_token": tokens["access_token"],
        "token_type": "bearer",
        "user": _account_payload(account),
    }
