"""Custom fields (Plan/14 A2): zero-code admin-defined patient/visit fields.

Values live inline as JSON on the entity (`custom_data`). Server validation:
unknown keys rejected, required present, type-coerced, select/multiselect
options enforced.
"""

import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.config import CustomField

VALID_TYPES = {"text", "textarea", "number", "date", "select", "multiselect", "boolean"}


def slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    if not slug:
        raise AppError("VALIDATION", "label must contain at least one latin letter")
    return slug[:60]


def create_key(db: Session, entity: str, label: str) -> str:
    base = slugify(label)
    key = base
    suffix = 2
    while db.scalar(select(CustomField.id).where(
        CustomField.entity == entity, CustomField.key == key
    )):
        key = f"{base}_{suffix}"
        suffix += 1
    return key


def active_fields(db: Session, entity: str) -> list[CustomField]:
    return list(
        db.scalars(
            select(CustomField)
            .where(CustomField.entity == entity, CustomField.is_active.is_(True))
            .order_by(CustomField.order, CustomField.id)
        ).all()
    )


def schema_payload(db: Session, entity: str) -> list[dict]:
    return [
        {
            "id": f.id,
            "key": f.key,
            "label": f.label,
            "label_ar": f.label_ar,
            "type": f.type,
            "options": f.options,
            "is_required": f.is_required,
            "order": f.order,
        }
        for f in active_fields(db, entity)
    ]


def _coerce(field: CustomField, value: Any) -> Any:
    if field.type == "boolean":
        if not isinstance(value, bool):
            raise AppError("VALIDATION", f"{field.key}: expected boolean")
        return value
    if field.type == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            raise AppError("VALIDATION", f"{field.key}: expected number") from None
    if field.type == "date":
        if isinstance(value, date | datetime):
            return value.isoformat()
        try:
            return date.fromisoformat(str(value)).isoformat()
        except ValueError:
            raise AppError("VALIDATION", f"{field.key}: expected date") from None
    if field.type == "select":
        if value not in (field.options or []):
            raise AppError("VALIDATION", f"{field.key}: value not in allowed options")
        return value
    if field.type == "multiselect":
        if not isinstance(value, list):
            raise AppError("VALIDATION", f"{field.key}: expected a list")
        allowed = set(field.options or [])
        if any(v not in allowed for v in value):
            raise AppError("VALIDATION", f"{field.key}: value not in allowed options")
        return value
    # text / textarea
    if not isinstance(value, str):
        raise AppError("VALIDATION", f"{field.key}: expected text")
    return value


def validate_and_coerce(db: Session, entity: str, custom_data: dict | None) -> dict | None:
    """F2: returns the coerced dict for storage (None if no data provided)."""
    if custom_data is None:
        return None
    if not isinstance(custom_data, dict):
        raise AppError("VALIDATION", "custom_data must be an object")
    fields = {f.key: f for f in active_fields(db, entity)}
    unknown = [k for k in custom_data if k not in fields]
    if unknown:
        raise AppError("VALIDATION", f"unknown custom fields: {', '.join(sorted(unknown))}")
    coerced: dict[str, Any] = {}
    for key, field in fields.items():
        if key in custom_data and custom_data[key] is not None:
            coerced[key] = _coerce(field, custom_data[key])
        elif field.is_required:
            raise AppError("VALIDATION", f"{field.label} is required")
    return coerced or None
