"""Patient-accessible documents (Plan/14 C10).

Staff share a rendered visit document (rx/report/sick_leave/referral) with
the patient; the patient sees it under their account and opens it via a
signed token without staff credentials.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import (
    AuditDbDep,
    DbDep,
    get_current_patient,
    get_request_id,
    require_perm,
)
from app.core.errors import AppError
from app.models.emr import Visit
from app.models.identity import PatientAccount, PatientProfile, StaffUser
from app.services import printing as printing_service

router = APIRouter(prefix="/api", tags=["shared-docs"])
sharer = Annotated[StaffUser, Depends(require_perm("emr.share_doc"))]
Patient = Annotated[PatientAccount, Depends(get_current_patient)]

DOC_KEYS = ("rx", "report", "sick_leave", "referral")
TOKEN_TTL = timedelta(days=30)


def _share_token(doc_key: str, visit_id: int, profile_id: int) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": f"shared:{doc_key}:{visit_id}:{profile_id}",
        "iat": now,
        "exp": now + TOKEN_TTL,
    }
    return jwt.encode(claims, get_settings().SECRET_KEY, algorithm=get_settings().TOKEN_ALG)


def _verify_share_token(token: str, doc_key: str, visit_id: int, profile_id: int) -> None:
    try:
        claims = jwt.decode(token, get_settings().SECRET_KEY,
                            algorithms=[get_settings().TOKEN_ALG])
    except jwt.PyJWTError as exc:
        raise AppError("FORBIDDEN", "invalid share token") from exc
    if claims.get("sub") != f"shared:{doc_key}:{visit_id}:{profile_id}":
        raise AppError("FORBIDDEN", "share token mismatch")


@router.post("/visits/{visit_id}/documents/share")
def share_visit_document(
    visit_id: int,
    current: sharer,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
    key: Annotated[str, Query(pattern="^(rx|report|sick_leave|referral)$")],
):
    visit = db.get(Visit, visit_id)
    if visit is None:
        raise AppError("NOT_FOUND", "visit not found")
    # render once to validate the document is printable
    printing_service.render_document(db, key, visit_id, "ar")
    shared = list(visit.documents_shared or [])
    if key not in shared:
        shared.append(key)
        visit.documents_shared = shared
        db.commit()
    token = _share_token(key, visit_id, visit.patient_profile_id)
    from app.audit import service as audit

    audit.access(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="document.shared", entity_type="visit", entity_id=str(visit_id),
        correlation_id=get_request_id(request),
    )
    return {"doc_key": key, "visit_id": visit_id, "token": token}


@router.get("/patient/documents")
def list_patient_documents(current: Patient, db: DbDep):
    profiles = db.scalars(
        select(PatientProfile).where(PatientProfile.account_id == current.id)
    ).all()
    profile_ids = [p.id for p in profiles]
    if not profile_ids:
        return {"items": []}
    visits = db.scalars(
        select(Visit).where(
            Visit.patient_profile_id.in_(profile_ids),
            Visit.documents_shared.is_not(None),
        ).order_by(Visit.id.desc())
    ).all()
    items = []
    for visit in visits:
        for doc_key in (visit.documents_shared or []):
            items.append({
                "doc_key": doc_key,
                "visit_id": visit.id,
                "visit_date": visit.started_at.isoformat() if visit.started_at else None,
                "patient_name": next((p.full_name for p in profiles
                                      if p.id == visit.patient_profile_id), None),
                "token": _share_token(doc_key, visit.id, visit.patient_profile_id),
            })
    return {"items": items}


@router.get("/patient/documents/{doc_key}/{visit_id}", response_class=HTMLResponse)
def open_patient_document(
    doc_key: str,
    visit_id: int,
    current: Patient,
    db: DbDep,
    token: Annotated[str, Query()],
    locale: Annotated[str, Query(pattern="^(ar|en)$")] = "ar",
):
    if doc_key not in DOC_KEYS:
        raise AppError("NOT_FOUND", "unknown document")
    visit = db.get(Visit, visit_id)
    if visit is None or visit.patient_profile_id not in {
        p.id for p in db.scalars(select(PatientProfile).where(
            PatientProfile.account_id == current.id)).all()
    }:
        raise AppError("FORBIDDEN", "document not accessible to this account")
    if doc_key not in (visit.documents_shared or []):
        raise AppError("FORBIDDEN", "document was not shared")
    _verify_share_token(token, doc_key, visit_id, visit.patient_profile_id)
    html = printing_service.render_document(db, doc_key, visit_id, locale)
    return HTMLResponse(html)
