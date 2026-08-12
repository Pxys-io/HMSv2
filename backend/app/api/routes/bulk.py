"""Bulk patient actions (Plan/14 C9)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.models.identity import PatientProfile, StaffUser
from app.models.tags import PatientTag
from app.services.activity import log_activity

router = APIRouter(prefix="/api/patients/bulk", tags=["bulk"])
editor = Annotated[StaffUser, Depends(require_perm("patient.edit"))]
archiver = Annotated[StaffUser, Depends(require_perm("patient.archive"))]


def _load_profiles(db: Session, ids: list[int]) -> tuple[list[PatientProfile], list[int]]:
    if not ids:
        raise AppError("VALIDATION", "profile_ids must not be empty")
    if len(ids) > 200:
        raise AppError("VALIDATION", "max 200 profiles per bulk call")
    found = db.scalars(
        select(PatientProfile).where(PatientProfile.id.in_(ids))
    ).all()
    by_id = {p.id: p for p in found}
    success = [by_id[i] for i in ids if i in by_id]
    failed = [i for i in ids if i not in by_id]
    return success, failed


@router.post("/tag")
def bulk_tag(body: dict, current: editor, request: Request, db: DbDep, audit_db: AuditDbDep):
    tag = db.get(PatientTag, body.get("tag_id"))
    if tag is None:
        raise AppError("NOT_FOUND", "tag not found")
    profiles, failed = _load_profiles(db, body.get("profile_ids", []))
    for p in profiles:
        if tag not in p.tags:
            p.tags.append(tag)
    db.commit()
    audit.access(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="bulk.tag", entity_type="bulk", entity_id=str(tag.id),
        correlation_id=get_request_id(request),
    )
    return {"success": [p.id for p in profiles], "failed": failed}


@router.post("/untag")
def bulk_untag(body: dict, current: editor, request: Request, db: DbDep, audit_db: AuditDbDep):
    tag = db.get(PatientTag, body.get("tag_id"))
    if tag is None:
        raise AppError("NOT_FOUND", "tag not found")
    profiles, failed = _load_profiles(db, body.get("profile_ids", []))
    for p in profiles:
        if tag in p.tags:
            p.tags.remove(tag)
    db.commit()
    audit.access(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="bulk.untag", entity_type="bulk", entity_id=str(tag.id),
        correlation_id=get_request_id(request),
    )
    return {"success": [p.id for p in profiles], "failed": failed}


@router.post("/delete")
def bulk_delete(body: dict, current: archiver, request: Request, db: DbDep, audit_db: AuditDbDep):
    """Soft archive of many profiles (permission patient.archive)."""
    profiles, failed = _load_profiles(db, body.get("profile_ids", []))
    for p in profiles:
        if not p.is_archived:
            p.is_archived = True
            log_activity(db, patient_profile_id=p.id, type="patient.archived",
                         actor_id=current.id, actor_label=current.email, source="bulk")
    db.commit()
    audit.access(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="bulk.delete", entity_type="bulk", entity_id=str(len(profiles)),
        correlation_id=get_request_id(request),
    )
    return {"success": [p.id for p in profiles], "failed": failed}
