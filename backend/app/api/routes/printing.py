"""Printing, recall, and search routes (Plan/07 §3–5)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.audit import service as audit
from app.core.config import get_settings
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.models.comms import PrintTemplate
from app.models.identity import StaffUser
from app.schemas.emr import (  # noqa: F401 (kept for template editor parity)
    MedicationCreate,
    MedicationUpdate,
)
from app.services import printing as printing_service
from app.services import recalls as recalls_service
from app.services import search as search_service

router = APIRouter(prefix="/api", tags=["print-recalls-search"])
staff = Annotated[StaffUser, Depends(require_perm("patient.view"))]
admin = Annotated[StaffUser, Depends(require_perm("admin.templates"))]


def _print_token(key: str, entity_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": f"print:{key}:{entity_id}", "iat": now, "exp": now + timedelta(seconds=60)},
        settings.SECRET_KEY,
        algorithm=settings.TOKEN_ALG,
    )


def _verify_print_token(token: str, key: str, entity_id: int) -> None:
    settings = get_settings()
    try:
        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.TOKEN_ALG])
    except jwt.PyJWTError:
        raise AppError("FORBIDDEN", "invalid print token") from None
    if claims.get("sub") != f"print:{key}:{entity_id}":
        raise AppError("FORBIDDEN", "print token mismatch")


@router.post("/print/token")
def issue_print_token(
    current: staff,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
    key: Annotated[str, Query(pattern="^(rx|report|sick_leave|referral|invoice)$")],
    entity_id: Annotated[int, Query()],
):
    """Issues a single-purpose 60s token so the browser can open the print
    page in a new tab without the bearer token (Plan/09 §8)."""
    # P4: secretary may print rx/invoice only; clinical composition is
    # doctor/admin.
    if current.role == "secretary" and key not in ("rx", "invoice"):
        raise AppError("FORBIDDEN", "secretaries may print prescriptions and invoices only")
    audit.access(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="print.token_issued", entity_type=key, entity_id=str(entity_id),
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    return {"token": _print_token(key, entity_id)}


@router.get("/print/{key}/{entity_id}", response_class=HTMLResponse)
def render_print(
    key: str,
    entity_id: int,
    db: DbDep,
    audit_db: AuditDbDep,
    token: Annotated[str, Query()],
    locale: Annotated[str, Query(pattern="^(ar|en)$")] = "ar",
):
    _verify_print_token(token, key, entity_id)
    html = printing_service.render_document(db, key, entity_id, locale)
    audit.access(
        audit_db,
        actor_type="system", actor_id=None, actor_label="print",
        action=f"print.{key}", entity_type=key, entity_id=str(entity_id),
        correlation_id=uuid.uuid4().hex,
    )
    return HTMLResponse(html)


# ---------------------------------------------------------------- templates


@router.get("/print-templates")
def list_templates(current: admin, db: DbDep):
    rows = db.scalars(select(PrintTemplate).order_by(PrintTemplate.key, PrintTemplate.locale)).all()
    return [
        {"id": t.id, "key": t.key, "locale": t.locale, "title": t.title,
         "body_html": t.body_html, "is_active": t.is_active}
        for t in rows
    ]


@router.put("/print-templates/{template_id}")
def update_template(
    template_id: int,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
    body: dict,
):
    template = db.get(PrintTemplate, template_id)
    if template is None:
        raise AppError("NOT_FOUND", "template not found")
    new_body = body.get("body_html")
    if new_body is None:
        raise AppError("VALIDATION", "body_html required")
    printing_service.validate_template_html(new_body)
    before = {"body": template.body_html[:80]}
    template.body_html = new_body
    template.sanitized_at = datetime.now(UTC)
    from app.audit import service as audit_mod

    with audit_mod.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="print_template.update", correlation_id=get_request_id(request),
        entity_type="print_template", entity_id=str(template_id),
        before=before, after={"body": new_body[:80]},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return {"id": template.id, "sanitized_at": template.sanitized_at.isoformat()}


# -------------------------------------------------------------------- recalls


@router.get("/recalls")
def list_recalls(current: staff, db: DbDep, lookahead: int | None = Query(default=None)):
    return recalls_service.recall_list(db, lookahead)


@router.post("/recalls/{visit_id}/dismiss")
def dismiss_recall(
    visit_id: int,
    current: staff,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
    days: int = Query(default=30, ge=1, le=365),
):
    result = recalls_service.dismiss(db, visit_id, days)
    audit.access(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="recall.dismiss", entity_type="visit", entity_id=str(visit_id),
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    return result


# -------------------------------------------------------------------- search


@router.get("/search/patients")
def patient_search(
    current: staff,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=8, ge=1, le=20),
    tag_id: int | None = Query(default=None),
):
    results = search_service.search_patients(db, q, limit, tag_id=tag_id)
    audit.access(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="search.patients", entity_type="search", entity_id=q[:60],
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    return {"query": q, "results": results}
