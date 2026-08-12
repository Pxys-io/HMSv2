"""Sophisticated patient form builder (JSON schema stored in the DB).

The patient form is defined by a JSON field list in the `patient_form.fields`
setting. Each field maps to either a FIXED `patient_profile` column or to the
flexible `custom_data` JSON column — so clinics can redesign the intake form
(rename, reorder, hide, group, type, options, validation) without schema
changes. `custom_data` keys are validated against the CustomField catalog.
"""

import re
from datetime import date

from app.core.errors import AppError
from app.services.custom_fields import validate_and_coerce
from app.services.settings import get_setting

FIXED_FIELDS = {
    "full_name": {"label_en": "Full name", "label_ar": "الاسم الكامل",
                  "type": "text", "required": True, "width": "half", "group": "Personal"},
    "phone": {"label_en": "Phone", "label_ar": "رقم الهاتف",
              "type": "tel", "required": True, "width": "half", "group": "Personal"},
    "full_name_ar": {"label_en": "Full name (Arabic)", "label_ar": "الاسم بالعربية",
                     "type": "text", "required": False, "width": "half", "group": "Personal"},
    "gender": {"label_en": "Gender", "label_ar": "الجنس",
               "type": "select", "required": False, "width": "half", "group": "Personal",
               "options": ["male", "female", "other", "unknown", "prefer_not_to_say"]},
    "birth_date": {"label_en": "Birth date", "label_ar": "تاريخ الميلاد",
                   "type": "date", "required": False, "width": "half", "group": "Personal"},
    "phone_alt": {"label_en": "Alternative phone", "label_ar": "هاتف بديل",
                  "type": "tel", "required": False, "width": "half", "group": "Contact"},
    "address": {"label_en": "Address", "label_ar": "العنوان",
                "type": "textarea", "required": False, "width": "full", "group": "Contact"},
    "allergies": {"label_en": "Allergies", "label_ar": "الحساسية",
                  "type": "textarea", "required": False, "width": "full", "group": "Alerts",
                  "help": "Known drug/food allergies"},
    "chronic_conditions": {
        "label_en": "Chronic conditions", "label_ar": "الأمراض المزمنة",
        "type": "textarea", "required": False, "width": "full", "group": "Alerts",
    },
}

FIXED_TYPES = {"text", "tel", "textarea", "number", "date", "select", "multiselect",
               "boolean", "photo", "file", "annotation", "audio"}
FIXED_COLUMNS = set(FIXED_FIELDS.keys())


def form_fields(db) -> list[dict]:
    """Merged field config: stored overrides + defaults for anything missing."""
    stored = get_setting(db, "patient_form.fields", None)
    if not isinstance(stored, list) or not stored:
        return [dict({"key": key, **meta}, enabled=True) for key, meta in FIXED_FIELDS.items()]
    defaults = {k: v for k, v in FIXED_FIELDS.items()}
    merged = []
    seen: set[str] = set()
    for row in stored:
        if not isinstance(row, dict) or not row.get("key"):
            continue
        key = row["key"]
        if key in seen:
            continue
        seen.add(key)
        base = dict(defaults.get(key, {
            "label_en": key, "label_ar": "", "type": "text",
            "required": False, "width": "full", "group": "Other",
        }))
        base.update({k: v for k, v in row.items() if k in (
            "key", "label_en", "label_ar", "type", "required", "enabled",
            "options", "width", "group", "help", "default", "min", "max", "pattern",
        )})
        merged.append(base)
    for key, meta in FIXED_FIELDS.items():
        if key not in seen:
            merged.append(dict({"key": key, **meta}, enabled=True))

    return merged


def enabled_fields(db) -> list[dict]:
    return [f for f in form_fields(db) if f.get("enabled", True)]


def _coerce_fixed(field: dict, value):
    """Type/option coercion for a fixed column value (None passes through)."""
    if value is None:
        return None
    ftype = field.get("type")
    if ftype in ("number",):
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise AppError("VALIDATION", f"{field['key']}: expected a number") from exc
    if ftype == "date":
        try:
            return date.fromisoformat(str(value))
        except ValueError as exc:
            raise AppError("VALIDATION", f"{field['key']}: expected YYYY-MM-DD") from exc
    if ftype in ("select", "multiselect"):
        options = field.get("options") or []
        if ftype == "select":
            if value not in options:
                raise AppError("VALIDATION", f"{field['key']}: must be one of {options}")
        else:
            if not isinstance(value, list) or any(v not in options for v in value):
                raise AppError("VALIDATION", f"{field['key']}: must be from {options}")
        return value
    if ftype == "boolean":
        if not isinstance(value, bool):
            raise AppError("VALIDATION", f"{field['key']}: expected true/false")
        return value
    text = str(value)
    if field.get("pattern") and not re.fullmatch(str(field["pattern"]), text):
        raise AppError("VALIDATION", f"{field['key']}: invalid format")
    length = len(text)
    if field.get("min") is not None and length < int(field["min"]):
        raise AppError("VALIDATION", f"{field['key']}: too short (min {field['min']})")
    if field.get("max") is not None and length > int(field["max"]):
        raise AppError("VALIDATION", f"{field['key']}: too long (max {field['max']})")
    return text


def validate_payload(db, payload: dict, *, partial: bool = False) -> dict:
    """Splits an incoming patient payload into {fixed, custom_data} with
    full validation against the configured form. Unknown keys are rejected."""
    fields = {f["key"]: f for f in enabled_fields(db)}
    fixed_out: dict = {}
    had_custom = "custom_data" in payload
    custom_payload: dict = {}
    for k, v in (payload.pop("custom_data", None) or {}).items():
        custom_payload[k] = v
    unknown = [k for k in payload if k not in fields]
    if unknown:
        raise AppError("VALIDATION", f"unknown fields: {', '.join(sorted(unknown))}")
    for key, value in payload.items():
        field = fields[key]
        if key in FIXED_COLUMNS:
            fixed_out[key] = _coerce_fixed(field, value)
        else:
            custom_payload[key] = value
    if not partial:
        missing = [
            f["key"] for f in fields.values()
            if f.get("required") and (f["key"] not in payload
                                      or payload[f["key"]] in (None, ""))
        ]
        if missing:
            raise AppError("VALIDATION", "required fields missing: " + ", ".join(sorted(missing)))
    if had_custom or custom_payload:
        custom_payload = validate_and_coerce(db, "patient", custom_payload)
    return {"fixed": fixed_out, "custom_data": custom_payload or None}
