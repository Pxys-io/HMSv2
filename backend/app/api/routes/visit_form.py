"""Visit form designer endpoints (high-grade customizability).

GET  /api/visit-form/sections   — ordered config for any clinical staff
PUT  /api/visit-form/sections   — save the config (admin)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.models.config import Setting
from app.models.identity import StaffUser
from app.services.visit_form import DEFAULT_SECTIONS, form_sections

router = APIRouter(prefix="/api/visit-form", tags=["visit-form"])
viewer = Annotated[StaffUser, Depends(require_perm("emr.view"))]
admin = Annotated[StaffUser, Depends(require_perm("admin.settings"))]

ALLOWED_KEYS = {"key", "label_en", "label_ar", "type", "required", "enabled", "options"}
ALLOWED_TYPES = {"text", "textarea", "number", "date", "select", "multiselect", "boolean"}
BUILTIN_TYPES = {"text", "textarea", "number", "date"}


def _payload(db) -> dict:
    return {
        "sections": form_sections(db),
        "builtin_keys": [s["key"] for s in DEFAULT_SECTIONS],
    }


@router.get("/sections")
def get_sections(current: viewer, db: DbDep):
    return _payload(db)


@router.put("/sections")
def put_sections(
    body: dict, current: admin, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    sections = body.get("sections")
    if not isinstance(sections, list):
        raise AppError("VALIDATION", "sections must be a list")
    cleaned = []
    for i, row in enumerate(sections):
        if not isinstance(row, dict) or not str(row.get("key", "")).strip():
            raise AppError("VALIDATION", f"sections[{i}]: key is required")
        key = str(row["key"]).strip()
        if len(key) > 60:
            raise AppError("VALIDATION", f"sections[{i}]: key too long")
        entry = {"key": key}
        for field in ("label_en", "label_ar"):
            value = row.get(field)
            entry[field] = str(value).strip() if value else (key if field == "label_en" else "")
        entry["type"] = row.get("type", "textarea")
        if entry["type"] not in ALLOWED_TYPES:
            raise AppError("VALIDATION", f"sections[{i}]: bad type")
        entry["required"] = bool(row.get("required"))
        entry["enabled"] = bool(row.get("enabled", True))
        if row.get("options") is not None:
            options = row["options"]
            if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
                raise AppError("VALIDATION", f"sections[{i}]: options must be a string list")
            entry["options"] = options
        cleaned.append(entry)
    row = db.scalar(select(Setting).where(Setting.key == "visit_form.sections"))
    if row is None:
        db.add(Setting(key="visit_form.sections", value=cleaned))
    else:
        row.value = cleaned
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="visit_form.update", correlation_id=get_request_id(request),
        entity_type="visit_form", entity_id="sections",
        after={"count": len(cleaned)},
    ):
        db.commit()
    return _payload(db)
