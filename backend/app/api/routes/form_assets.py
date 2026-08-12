"""Form asset upload/serve endpoints (massive form builder).

POST /api/form-assets/{entity}/{entity_id}   upload a field artifact (staff)
POST /api/form-assets/template               upload an annotation template (admin)
GET  /api/form-assets/template/{template_id} serve a template image (staff)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import Response

from app.core.deps import DbDep, require_perm
from app.core.errors import AppError
from app.models.config import FormAssetTemplate
from app.models.emr import Visit
from app.models.identity import PatientProfile, StaffUser
from app.services import attachments as attachments_service
from app.services import form_assets as asset_service

router = APIRouter(prefix="/api/form-assets", tags=["form-assets"])
editor = Annotated[StaffUser, Depends(require_perm("patient.edit"))]
admin = Annotated[StaffUser, Depends(require_perm("admin.settings"))]


@router.post("/{entity}/{entity_id}")
def upload_form_asset(
    entity: str,
    entity_id: int,
    current: editor,
    db: DbDep,
    file: UploadFile,
    title: str | None = Query(default=None),
):
    """Uploads a form-field artifact (photo/file/annotation/audio) through
    the quarantined attachment pipeline; returns the file reference to store
    as the field value."""
    if entity == "patient":
        profile = db.get(PatientProfile, entity_id)
        if profile is None:
            raise AppError("NOT_FOUND", "patient not found")
        profile_id, visit_id = profile.id, None
    elif entity == "visit":
        visit = db.get(Visit, entity_id)
        if visit is None:
            raise AppError("NOT_FOUND", "visit not found")
        profile_id, visit_id = visit.patient_profile_id, visit.id
    else:
        raise AppError("VALIDATION", "entity must be patient or visit")
    attachment = attachments_service.store_upload(
        db,
        profile_id=profile_id,
        visit_id=visit_id,
        kind="form",
        title=title,
        file=file,
        uploaded_by_id=current.id,
    )
    db.commit()
    return {
        "file_id": attachment.id,
        "mime": attachment.mime,
        "size_bytes": attachment.size_bytes,
        "scan_status": attachment.scan_status,
    }


@router.post("/template")
def upload_template(
    current: admin,
    db: DbDep,
    file: UploadFile,
):
    template = asset_service.store_template(file, current.id)
    db.add(template)
    db.commit()
    return {"template_file_id": template.id, "mime": template.mime}


@router.get("/template/{template_id}")
def serve_template(template_id: int, current: editor, db: DbDep):
    template = db.get(FormAssetTemplate, template_id)
    if template is None:
        raise AppError("NOT_FOUND", "template not found")
    return Response(
        content=asset_service.read_template(template),
        media_type=template.mime,
        headers={"Cache-Control": "private, no-store"},
    )
