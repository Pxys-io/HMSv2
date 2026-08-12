"""Duplicate detection + merge + archive endpoints (Plan/14 C8)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.models.duplicates import DuplicateGroup
from app.models.identity import PatientProfile, StaffUser
from app.services import duplicates as dup_service
from app.services.activity import log_activity

router = APIRouter(prefix="/api", tags=["duplicates"])
viewer = Annotated[StaffUser, Depends(require_perm("ops.duplicates"))]
archiver = Annotated[StaffUser, Depends(require_perm("patient.archive"))]


@router.get("/duplicates")
def list_duplicates(
    current: viewer, db: DbDep,
    status: str = Query(default="open", pattern="^(open|merged|rejected)$"),
):
    return {"items": dup_service.list_groups(db, status)}


@router.post("/duplicates/refresh")
def refresh_duplicates(
    current: viewer, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    count = dup_service.refresh_detection(db)
    audit.access(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="duplicates.refresh", entity_type="duplicates", entity_id=str(count),
        correlation_id=get_request_id(request),
    )
    return {"groups": count}


@router.post("/duplicates/{group_id}/accept")
def accept_duplicates(
    group_id: int, current: viewer, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    group = db.get(DuplicateGroup, group_id)
    if group is None or group.status != "open":
        raise AppError("NOT_FOUND", "open duplicate group not found")
    dup_service.merge_group(db, group, current.id)
    audit.access(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="duplicates.merge", entity_type="duplicates", entity_id=str(group_id),
        correlation_id=get_request_id(request),
    )
    return {"ok": True, "status": "merged"}


@router.post("/duplicates/{group_id}/reject")
def reject_duplicates(
    group_id: int, current: viewer, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    group = db.get(DuplicateGroup, group_id)
    if group is None or group.status != "open":
        raise AppError("NOT_FOUND", "open duplicate group not found")
    group.status = "rejected"
    group.resolved_by = current.id
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="duplicates.reject", correlation_id=get_request_id(request),
        entity_type="duplicates", entity_id=str(group_id),
    ):
        db.commit()
    return {"ok": True}


@router.post("/patients/{profile_id}/archive")
def archive_patient(
    profile_id: int, current: archiver, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    profile = db.get(PatientProfile, profile_id)
    if profile is None:
        raise AppError("NOT_FOUND", "patient profile not found")
    if profile.is_archived:
        raise AppError("VALIDATION", "already archived")
    profile.is_archived = True
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="patient.archive", correlation_id=get_request_id(request),
        entity_type="patient_profile", entity_id=str(profile_id),
    ):
        db.commit()
    log_activity(db, patient_profile_id=profile_id, type="patient.archived",
                 actor_id=current.id, actor_label=current.email)
    return {"ok": True}


@router.post("/patients/{profile_id}/unarchive")
def unarchive_patient(
    profile_id: int, current: archiver, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    profile = db.get(PatientProfile, profile_id)
    if profile is None:
        raise AppError("NOT_FOUND", "patient profile not found")
    if not profile.is_archived:
        raise AppError("VALIDATION", "not archived")
    profile.is_archived = False
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="patient.unarchive", correlation_id=get_request_id(request),
        entity_type="patient_profile", entity_id=str(profile_id),
    ):
        db.commit()
    log_activity(db, patient_profile_id=profile_id, type="patient.unarchived",
                 actor_id=current.id, actor_label=current.email)
    return {"ok": True}
