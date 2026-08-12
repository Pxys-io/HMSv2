"""Visit form designer (Plan/14 high-grade customizability).

The 8 built-in sections live on fixed `visit` columns; this config controls
their order, labels (AR/EN), visibility and required-ness. Extra custom
sections come from the existing CustomField system (entity=visit) and are
stored/validated via `custom_data`.
"""

from app.core.errors import AppError
from app.services.settings import get_setting

DEFAULT_SECTIONS = [
    {"key": "chief_complaint", "label_en": "Chief complaint", "label_ar": "الشكوى الرئيسية",
     "type": "textarea", "required": False, "enabled": True},
    {"key": "history", "label_en": "History", "label_ar": "التاريخ المرضي",
     "type": "textarea", "required": False, "enabled": True},
    {"key": "clinical_exam", "label_en": "Clinical exam", "label_ar": "الفحص الإكلينيكي",
     "type": "textarea", "required": False, "enabled": True},
    {"key": "findings", "label_en": "Findings", "label_ar": "النتائج",
     "type": "textarea", "required": False, "enabled": True},
    {"key": "labs", "label_en": "Labs", "label_ar": "التحاليل",
     "type": "textarea", "required": False, "enabled": True},
    {"key": "imaging", "label_en": "Imaging", "label_ar": "الأشعة",
     "type": "textarea", "required": False, "enabled": True},
    {"key": "plan", "label_en": "Plan", "label_ar": "الخطة العلاجية",
     "type": "textarea", "required": False, "enabled": True},
    {"key": "notes_next_visit", "label_en": "Notes for next visit",
     "label_ar": "ملاحظات الزيارة القادمة",
     "type": "textarea", "required": False, "enabled": True},
]

BUILTIN_KEYS = {s["key"] for s in DEFAULT_SECTIONS}


def form_sections(db) -> list[dict]:
    """Returns the ordered, merged section config (missing keys defaulted)."""
    stored = get_setting(db, "visit_form.sections", None)
    if not isinstance(stored, list) or not stored:
        return DEFAULT_SECTIONS
    defaults = {s["key"]: s for s in DEFAULT_SECTIONS}
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
            "key": key, "label_en": key, "label_ar": key, "type": "textarea",
        }))
        base.update({k: v for k, v in row.items() if k in (
            "key", "label_en", "label_ar", "type", "required", "enabled", "options"
        )})
        merged.append(base)
    for s in DEFAULT_SECTIONS:
        if s["key"] not in seen:
            merged.append(s)
    return merged


def enabled_sections(db) -> list[dict]:
    return [s for s in form_sections(db) if s.get("enabled", True)]


def check_required_on_complete(db, visit) -> None:
    """Blocks completion when a required section is empty (high-grade form
    rules; nothing is required by default)."""
    missing = []
    for section in enabled_sections(db):
        if not section.get("required"):
            continue
        key = section["key"]
        if key in BUILTIN_KEYS:
            value = getattr(visit, key, None)
        else:
            value = (visit.custom_data or {}).get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(section.get("label_en") or key)
    if missing:
        raise AppError(
            "VALIDATION",
            "required fields missing: " + ", ".join(sorted(missing)),
        )
