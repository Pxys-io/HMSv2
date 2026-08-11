"""Visit routes (Plan/05 §3): create, read (role-scoped), versioned patch,
diagnoses, complete, reopen, prescription, timeline, attachments."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_role
from app.core.errors import AppError
from app.models.emr import Attachment, Visit
from app.models.identity import PatientProfile, StaffUser
from app.schemas.emr import (
    DiagnosisPut,
    PrescriptionPut,
    VisitCreate,
    VisitPatch,
)
from app.services import attachments as attachments_service
from app.services import visits as visit_service
from app.services.idempotency import claim, complete, get_key_from_request

router = APIRouter(prefix="/api", tags=["visits"])
doctor = Annotated[StaffUser, Depends(require_role("doctor", "admin"))]
staff_any = Annotated[StaffUser, Depends(require_role("admin", "doctor", "secretary"))]


def _replay_response(
    request: Request, response: Response, db: Session, actor: StaffUser, payload: dict
) -> bool:
    key = get_key_from_request(request)
    if not key:
        return False
    replay = claim(db, owner_type="staff", owner_id=actor.id, key=key, payload=payload)
    if replay:
        response.status_code = replay["status"]
        response.body = json.dumps(replay["body"], ensure_ascii=False).encode()
        response.headers["Content-Type"] = "application/json"
        return True
    return False


def _finish_idem(request: Request, db: Session, actor: StaffUser, body: dict) -> None:
    key = get_key_from_request(request)
    if key:
        complete(db, owner_type="staff", owner_id=actor.id, key=key, status=200, body=body)


def _role_payload(db: Session, visit: Visit, viewer: StaffUser) -> dict:
    """Role-scoped visit projection (E2)."""
    base: dict = {
        "id": visit.id,
        "patient_profile_id": visit.patient_profile_id,
        "doctor_id": visit.doctor_id,
        "visit_type_id": visit.visit_type_id,
        "appointment_id": visit.appointment_id,
        "queue_entry_id": visit.queue_entry_id,
        "started_at": visit.started_at.isoformat() if visit.started_at else None,
        "ended_at": visit.ended_at.isoformat() if visit.ended_at else None,
        "status": visit.status,
        "record_version": visit.record_version,
        "follow_up_weeks": visit.follow_up_weeks,
        "follow_up_due": visit.follow_up_due.isoformat() if visit.follow_up_due else None,
    }
    if viewer.role == "secretary":
        profile = db.get(PatientProfile, visit.patient_profile_id)
        base["patient"] = {
            "id": profile.id,
            "code": profile.code,
            "full_name": profile.full_name,
            "phone": profile.phone,
        } if profile else None
        base["attachments"] = _attachment_metadata(db, visit)
        return base

    for field in (
        "chief_complaint", "history", "vitals", "clinical_exam", "findings",
        "labs", "imaging", "plan", "notes_next_visit",
    ):
        base[field] = getattr(visit, field)
    is_author = visit.last_saved_by == viewer.id or viewer.role == "admin"
    if is_author or viewer.role == "admin":
        base["notes_private"] = visit.notes_private
    base["diagnoses"] = _diagnosis_rows(db, visit.id)
    base["prescription"] = visit_service.get_prescription(db, visit.id)
    base["attachments"] = _attachment_metadata(db, visit)
    return base


def _attachment_metadata(db: Session, visit: Visit) -> list[dict]:
    rows = db.scalars(
        select(Attachment).where(Attachment.visit_id == visit.id).order_by(Attachment.id)
    ).all()
    return [
        {
            "id": a.id,
            "kind": a.kind,
            "title": a.title,
            "mime": a.mime,
            "size_bytes": a.size_bytes,
            "scan_status": a.scan_status,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]


def _diagnosis_rows(db: Session, visit_id: int) -> list[dict]:
    from app.models.emr import VisitDiagnosis

    rows = db.scalars(
        select(VisitDiagnosis)
        .where(VisitDiagnosis.visit_id == visit_id)
        .order_by(VisitDiagnosis.order)
    ).all()
    return [
        {"kind": d.kind, "label": d.label, "icd10_code": d.icd10_code, "notes": d.notes}
        for d in rows
    ]


@router.post("/visits")
def create_visit(
    body: VisitCreate,
    request: Request,
    response: Response,
    current: doctor,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if _replay_response(request, response, db, current, body.model_dump(mode="json")):
        return response
    visit = visit_service.create(
        db, audit_db, actor=current, correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
        queue_entry_id=body.queue_entry_id,
        patient_profile_id=body.patient_profile_id,
        visit_type_id=body.visit_type_id,
    )
    payload = _role_payload(db, visit, current)
    _finish_idem(request, db, current, payload)
    return payload


@router.get("/visits/{visit_id}")
def get_visit(visit_id: int, current: staff_any, request: Request, db: DbDep, audit_db: AuditDbDep):
    visit = visit_service.get_visit(db, visit_id)
    if current.role == "secretary":
        pass  # demographics + metadata only
    else:
        audit.access(
            audit_db,
            actor_type="staff", actor_id=current.id, actor_label=current.email,
            action="visit.read", entity_type="visit", entity_id=str(visit.id),
            correlation_id=get_request_id(request),
            ip=request.client.host if request.client else None,
        )
    return _role_payload(db, visit, current)


@router.patch("/visits/{visit_id}")
def patch_visit(
    visit_id: int,
    body: VisitPatch,
    request: Request,
    response: Response,
    current: doctor,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if _replay_response(request, response, db, current, body.model_dump(mode="json")):
        return response
    visit = visit_service.get_visit(db, visit_id)
    fields = {
        k: v
        for k, v in body.model_dump(exclude={"record_version"}).items()
        if k in body.model_fields_set
    }
    updated = visit_service.patch(
        db, audit_db, visit=visit, actor=current, correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
        fields=fields, expected_version=body.record_version,
    )
    payload = _role_payload(db, updated, current)
    _finish_idem(request, db, current, payload)
    return payload


@router.put("/visits/{visit_id}/diagnoses")
def put_diagnoses(
    visit_id: int,
    body: DiagnosisPut,
    request: Request,
    response: Response,
    current: doctor,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if _replay_response(request, response, db, current, body.model_dump(mode="json")):
        return response
    visit = visit_service.get_visit(db, visit_id)
    visit_service.set_diagnoses(
        db, audit_db, visit=visit, actor=current, correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
        items=[i.model_dump() for i in body.items], expected_version=body.record_version,
    )
    payload = {"record_version": visit.record_version, "diagnoses": _diagnosis_rows(db, visit.id)}
    _finish_idem(request, db, current, payload)
    return payload


@router.post("/visits/{visit_id}/complete")
def complete_visit(
    visit_id: int,
    request: Request,
    response: Response,
    current: doctor,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if _replay_response(request, response, db, current, {"visit_id": visit_id}):
        return response
    visit = visit_service.get_visit(db, visit_id)
    completed = visit_service.complete(
        db, audit_db, visit=visit, actor=current, correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    payload = _role_payload(db, completed, current)
    _finish_idem(request, db, current, payload)
    return payload


@router.post("/visits/{visit_id}/reopen")
def reopen_visit(
    visit_id: int,
    request: Request,
    response: Response,
    current: doctor,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if _replay_response(request, response, db, current, {"visit_id": visit_id}):
        return response
    visit = visit_service.get_visit(db, visit_id)
    reopened = visit_service.reopen(
        db, audit_db, visit=visit, actor=current, correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    payload = _role_payload(db, reopened, current)
    _finish_idem(request, db, current, payload)
    return payload


@router.put("/visits/{visit_id}/prescription")
def put_prescription(
    visit_id: int,
    body: PrescriptionPut,
    request: Request,
    response: Response,
    current: doctor,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if _replay_response(request, response, db, current, body.model_dump(mode="json")):
        return response
    visit = visit_service.get_visit(db, visit_id)
    rx = visit_service.put_prescription(
        db, audit_db, visit=visit, actor=current, correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
        notes=body.notes, items=[i.model_dump() for i in body.items],
        expected_version=body.record_version,
    )
    payload = {"record_version": visit.record_version, "prescription": rx}
    _finish_idem(request, db, current, payload)
    return payload


@router.get("/patients/{profile_id}/timeline")
def patient_timeline(
    profile_id: int,
    current: doctor,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if db.get(PatientProfile, profile_id) is None:
        raise AppError("NOT_FOUND", "patient profile not found")
    audit.access(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="timeline.read", entity_type="patient_profile", entity_id=str(profile_id),
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    return visit_service.timeline(db, profile_id, current)


@router.post("/visits/{visit_id}/attachments")
async def upload_visit_attachment(
    visit_id: int,
    request: Request,
    current: doctor,
    db: DbDep,
    audit_db: AuditDbDep,
    file: UploadFile,
    kind: str = "photo",
    title: str | None = None,
):
    visit = visit_service.get_visit(db, visit_id)
    attachment = attachments_service.store_upload(
        db,
        profile_id=visit.patient_profile_id,
        visit_id=visit.id,
        kind=kind,
        title=title,
        file=file,
        uploaded_by_id=current.id,
    )
    audit.access(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="attachment.upload", entity_type="attachment", entity_id=str(attachment.id),
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return {
        "id": attachment.id,
        "kind": attachment.kind,
        "title": attachment.title,
        "mime": attachment.mime,
        "size_bytes": attachment.size_bytes,
        "scan_status": attachment.scan_status,
    }
