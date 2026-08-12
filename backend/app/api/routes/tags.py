"""Patient tag/segment endpoints (Plan/14 C4)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete, select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.models.identity import PatientProfile, StaffUser
from app.models.tags import PatientTag, patient_tag

router = APIRouter(prefix="/api", tags=["tags"])
viewer = Annotated[StaffUser, Depends(require_perm("patient.view"))]
manager = Annotated[StaffUser, Depends(require_perm("ops.tag"))]


def _payload(tag: PatientTag) -> dict:
    return {
        "id": tag.id, "name": tag.name, "name_ar": tag.name_ar,
        "color": tag.color, "is_active": tag.is_active,
    }


@router.get("/tags")
def list_tags(current: viewer, db: DbDep):
    rows = db.scalars(
        select(PatientTag).where(PatientTag.is_active.is_(True)).order_by(PatientTag.name)
    ).all()
    return {"items": [_payload(t) for t in rows]}


@router.post("/tags")
def create_tag(body: dict, current: manager, request: Request, db: DbDep, audit_db: AuditDbDep):
    name = str(body.get("name", "")).strip()
    if not name:
        raise AppError("VALIDATION", "name is required")
    if db.scalar(select(PatientTag).where(PatientTag.name == name)):
        raise AppError("VALIDATION", f"tag '{name}' already exists")
    tag = PatientTag(name=name, name_ar=body.get("name_ar"), color=body.get("color"))
    db.add(tag)
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="tag.create", correlation_id=get_request_id(request),
        entity_type="tag", entity_id=str(tag.id), after={"name": name},
    ):
        db.commit()
    return _payload(tag)


@router.patch("/tags/{tag_id}")
def update_tag(tag_id: int, body: dict, current: manager, request: Request,
               db: DbDep, audit_db: AuditDbDep):
    tag = db.get(PatientTag, tag_id)
    if tag is None:
        raise AppError("NOT_FOUND", "tag not found")
    if "name" in body:
        tag.name = str(body["name"]).strip()
    if "name_ar" in body:
        tag.name_ar = body["name_ar"]
    if "color" in body:
        tag.color = body["color"]
    if "is_active" in body:
        tag.is_active = bool(body["is_active"])
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="tag.update", correlation_id=get_request_id(request),
        entity_type="tag", entity_id=str(tag_id),
    ):
        db.commit()
    return _payload(tag)


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: int, current: manager, request: Request,
               db: DbDep, audit_db: AuditDbDep):
    tag = db.get(PatientTag, tag_id)
    if tag is None:
        raise AppError("NOT_FOUND", "tag not found")
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="tag.delete", correlation_id=get_request_id(request),
        entity_type="tag", entity_id=str(tag_id),
    ):
        db.execute(delete(patient_tag).where(patient_tag.c.tag_id == tag_id))
        db.delete(tag)
        db.commit()
    return {"ok": True}


@router.put("/patients/{profile_id}/tags")
def set_patient_tags(
    profile_id: int, body: dict, current: manager, db: DbDep,
):
    profile = db.get(PatientProfile, profile_id)
    if profile is None:
        raise AppError("NOT_FOUND", "patient profile not found")
    tag_ids = body.get("tag_ids", [])
    tags = db.scalars(
        select(PatientTag).where(PatientTag.id.in_(tag_ids), PatientTag.is_active.is_(True))
    ).all()
    profile.tags = list(tags)
    db.commit()
    return {"tag_ids": [t.id for t in tags]}
