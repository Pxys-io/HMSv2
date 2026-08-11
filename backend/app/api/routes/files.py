"""Authenticated attachment file serving (Plan/05 E5).

Doctor/admin only, access-audited, `Cache-Control: private, no-store`,
and never served before a clean scan. Public assets never go through this
endpoint.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_role
from app.core.errors import AppError
from app.models.emr import Attachment
from app.models.identity import StaffUser

router = APIRouter(prefix="/api/files", tags=["files"])
clinical = Annotated[StaffUser, Depends(require_role("doctor", "admin"))]


@router.get("/{attachment_id}")
def get_file(
    attachment_id: int,
    current: clinical,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
    thumb: Annotated[bool, Query()] = False,
):
    attachment = db.get(Attachment, attachment_id)
    if attachment is None:
        raise AppError("NOT_FOUND", "attachment not found")
    if attachment.scan_status != "clean":
        raise AppError("CONFLICT", "file is quarantined (scan pending or rejected)")

    from pathlib import Path

    from app.core.config import get_settings

    settings = get_settings()
    rel = attachment.thumb_path if thumb and attachment.thumb_path else attachment.file_path
    path = Path(settings.UPLOAD_DIR) / rel
    if not path.is_file():
        raise AppError("NOT_FOUND", "file missing on disk")

    audit.access(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="attachment.download" if not thumb else "attachment.thumb",
        entity_type="attachment", entity_id=str(attachment.id),
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    return FileResponse(
        path,
        media_type=attachment.mime,
        headers={"Cache-Control": "private, no-store"},
    )
