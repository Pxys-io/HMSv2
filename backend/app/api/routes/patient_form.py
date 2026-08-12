"""Patient form designer endpoints (sophisticated JSON form schema).

GET  /api/patient-form   — the configured field list for staff UIs
PUT  /api/patient-form   — save the schema (admin)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.models.config import Setting
from app.models.identity import StaffUser
from app.services.patient_form import FIXED_FIELDS, form_fields

router = APIRouter(prefix="/api/patient-form", tags=["patient-form"])
viewer = Annotated[StaffUser, Depends(require_perm("patient.view"))]
admin = Annotated[StaffUser, Depends(require_perm("admin.settings"))]

ALLOWED_TYPES = {"text", "tel", "textarea", "number", "date", "select", "multiselect",
                 "boolean", "photo", "file", "annotation", "audio"}
ALLOWED_KEYS = {"key", "label_en", "label_ar", "type", "required", "enabled", "options",
                "width", "group", "help", "default", "min", "max", "pattern"}


@router.get("")
def get_form(current: viewer, db: DbDep):
    return {"fields": form_fields(db), "fixed_keys": list(FIXED_FIELDS.keys())}


@router.put("")
def put_form(
    body: dict, current: admin, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    fields = body.get("fields")
    if not isinstance(fields, list):
        raise AppError("VALIDATION", "fields must be a list")
    cleaned = []
    for i, row in enumerate(fields):
        if not isinstance(row, dict) or not str(row.get("key", "")).strip():
            raise AppError("VALIDATION", f"fields[{i}]: key is required")
        key = str(row["key"]).strip()
        if len(key) > 60:
            raise AppError("VALIDATION", f"fields[{i}]: key too long")
        entry = {"key": key}
        for f in ("label_en", "label_ar"):
            value = row.get(f)
            entry[f] = str(value).strip() if value else (key if f == "label_en" else "")
        entry["type"] = row.get("type", "text")
        if entry["type"] not in ALLOWED_TYPES:
            raise AppError("VALIDATION", f"fields[{i}]: bad type")
        entry["required"] = bool(row.get("required"))
        entry["enabled"] = bool(row.get("enabled", True))
        entry["width"] = row.get("width", "full")
        if entry["width"] not in ("half", "full"):
            raise AppError("VALIDATION", f"fields[{i}]: width must be half or full")
        entry["group"] = str(row.get("group", "Other")).strip() or "Other"
        for f in ("help", "default", "pattern"):
            if row.get(f) is not None:
                entry[f] = str(row[f])
        for f in ("min", "max"):
            if row.get(f) is not None:
                try:
                    entry[f] = int(row[f])
                except (TypeError, ValueError) as exc:
                    raise AppError("VALIDATION", f"fields[{i}]: {f} must be a number") from exc
        if row.get("options") is not None:
            options = row["options"]
            if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
                raise AppError("VALIDATION", f"fields[{i}]: options must be a string list")
            entry["options"] = options
        cleaned.append(entry)
    row = db.scalar(select(Setting).where(Setting.key == "patient_form.fields"))
    if row is None:
        db.add(Setting(key="patient_form.fields", value=cleaned))
    else:
        row.value = cleaned
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="patient_form.update", correlation_id=get_request_id(request),
        entity_type="patient_form", entity_id="fields",
        after={"count": len(cleaned)},
    ):
        db.commit()
    return {"fields": form_fields(db), "fixed_keys": list(FIXED_FIELDS.keys())}
