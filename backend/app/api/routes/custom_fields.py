"""Custom fields admin API (Plan/14 A2)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.models.config import CustomField
from app.models.identity import StaffUser
from app.services.custom_fields import create_key, schema_payload

router = APIRouter(prefix="/api/custom-fields", tags=["custom-fields"])
admin = Annotated[StaffUser, Depends(require_perm("admin.custom_fields"))]
staff = Annotated[StaffUser, Depends(require_perm("patient.view"))]


class CustomFieldCreate(BaseModel):
    entity: str = Field(pattern="^(patient|visit)$")
    label: str = Field(min_length=2, max_length=200)
    label_ar: str | None = None
    type: str = Field(pattern="^(text|textarea|number|date|select|multiselect|boolean)$")
    options: list | None = None
    is_required: bool = False
    order: int = 0


class CustomFieldUpdate(BaseModel):
    label: str | None = None
    label_ar: str | None = None
    type: str | None = None
    options: list | None = None
    is_required: bool | None = None
    order: int | None = None


def _payload(f: CustomField) -> dict:
    return {
        "id": f.id,
        "entity": f.entity,
        "key": f.key,
        "label": f.label,
        "label_ar": f.label_ar,
        "type": f.type,
        "options": f.options,
        "is_required": f.is_required,
        "is_active": f.is_active,
        "order": f.order,
    }


@router.get("")
def list_fields(current: admin, db: DbDep, entity: str = Query(pattern="^(patient|visit)$")):
    rows = db.scalars(
        select(CustomField)
        .where(CustomField.entity == entity)
        .order_by(CustomField.order, CustomField.id)
    ).all()
    return [_payload(f) for f in rows]


@router.get("/schema")
def field_schema(current: staff, db: DbDep, entity: str = Query(pattern="^(patient|visit)$")):
    """What the forms render — active fields only (F4: deactivated hidden)."""
    return {"entity": entity, "fields": schema_payload(db, entity)}


@router.post("")
def create_field(
    body: CustomFieldCreate,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if body.type in ("select", "multiselect") and not body.options:
        raise AppError("VALIDATION", "select/multiselect fields need options")
    key = create_key(db, body.entity, body.label)  # F1: auto key, unique
    field = CustomField(
        entity=body.entity,
        key=key,
        label=body.label,
        **body.model_dump(exclude={"entity", "label"}),
    )
    db.add(field)
    db.flush()
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="custom_field.create", correlation_id=get_request_id(request),
        entity_type="custom_field", entity_id=str(field.id),
        after={"entity": field.entity, "key": field.key, "type": field.type},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return _payload(field)


@router.patch("/{field_id}")
def update_field(
    field_id: int,
    body: CustomFieldUpdate,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    field = db.get(CustomField, field_id)
    if field is None:
        raise AppError("NOT_FOUND", "custom field not found")
    if body.type == "select" or body.type == "multiselect":
        options = body.options if body.options is not None else field.options
        if not options:
            raise AppError("VALIDATION", "select/multiselect fields need options")
    before = _payload(field)
    for attr in ("label", "label_ar", "type", "options", "is_required", "order"):
        if getattr(body, attr) is not None:
            setattr(field, attr, getattr(body, attr))
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="custom_field.update", correlation_id=get_request_id(request),
        entity_type="custom_field", entity_id=str(field_id),
        before=before, after=_payload(field),
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return _payload(field)


@router.post("/{field_id}/deactivate")
def deactivate_field(
    field_id: int,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    """F4: deactivate hides from forms; old values stay readable."""
    field = db.get(CustomField, field_id)
    if field is None:
        raise AppError("NOT_FOUND", "custom field not found")
    before = _payload(field)
    field.is_active = False
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="custom_field.deactivate", correlation_id=get_request_id(request),
        entity_type="custom_field", entity_id=str(field_id),
        before=before, after={"is_active": False},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return _payload(field)
