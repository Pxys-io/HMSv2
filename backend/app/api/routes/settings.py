"""Settings, public assets, and branding endpoints (Plan/09 admin, Plan/11).

- `GET/PUT /api/settings` (admin): read all known keys / update a partial
  dict; unknown keys rejected.
- `POST /api/public-assets` (admin) + `GET /api/public/assets/{id}`: public
  clinic logo / doctor photos — re-encoded, EXIF-stripped, never patient data.
- `GET /api/public/branding`: what the public site renders.
"""

import hashlib
import io
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select

from app.audit import service as audit
from app.core.config import get_settings
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.models.config import PublicAsset, Setting
from app.models.identity import StaffUser
from app.services.settings import DEFAULT_SETTINGS, get_setting

router = APIRouter(prefix="/api", tags=["settings-assets"])
admin = Annotated[StaffUser, Depends(require_perm("admin.settings"))]

KNOWN_KEYS = {
    "clinic.name", "clinic.address", "clinic.phones", "clinic.country_code",
    "clinic.timezone", "clinic.hours_text", "clinic.location_url",
    "billing.currency", "billing.discount_cap_secretary_pct",
    "billing.cashier_can_adjust_pricing",
    "billing.vat_rate_pct", "billing.vat_inclusive",
    "billing.vat_number", "billing.vat_exempt",
    "booking.horizon_days",
    "reminder.sms_gateway_url", "reminder.sms_token", "reminder.sms_sender",
    "patient_form.fields",
    "visit_form.sections",
    "vitals.reference_ranges",
    "petty_cash.opening_balance", "petty_cash.categories",
    "reminder.whatsapp_template_ar",
    "reminder.whatsapp_template_en", "public.about", "public.services",
}


@router.get("/settings")
def get_settings_all(current: admin, db: DbDep):
    rows = db.scalars(select(Setting)).all()
    stored = {row.key: row.value for row in rows}
    return {key: stored.get(key, DEFAULT_SETTINGS.get(key)) for key in KNOWN_KEYS}


@router.put("/settings")
def update_settings_all(
    body: dict,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    unknown = [k for k in body if k not in KNOWN_KEYS]
    if unknown:
        raise AppError("VALIDATION", f"unknown settings: {', '.join(sorted(unknown))}")
    before = {k: (get_setting(db, k, None)) for k in body}
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="settings.update", correlation_id=get_request_id(request),
        entity_type="settings", entity_id="clinic",
        before=before, after=body,
        ip=request.client.host if request.client else None,
    ):
        for key, value in body.items():
            row = db.scalar(select(Setting).where(Setting.key == key))
            if row is None:
                db.add(Setting(key=key, value=value))
            else:
                row.value = value
        db.commit()
    return {"updated": list(body.keys())}


# ------------------------------------------------------------------ assets


@router.post("/public-assets")
async def upload_public_asset(
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
    file: UploadFile,
    kind: Annotated[
        str, Query(pattern="^(clinic_logo|doctor_photo|public_image)$")
    ] = "public_image",
):
    data = file.file.read()
    if len(data) == 0 or len(data) > 5 * 1024 * 1024:
        raise AppError("VALIDATION", "file too large or empty")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise AppError("VALIDATION", "unreadable image") from exc
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    img.thumbnail((1024, 1024))  # public images never need full resolution

    settings = get_settings()
    directory = Path(settings.UPLOAD_DIR) / "public"
    directory.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex
    path = directory / f"{stem}.jpg"
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    path.write_bytes(out.getvalue())

    asset = PublicAsset(
        kind=kind,
        file_path=str(path.relative_to(Path(settings.UPLOAD_DIR))),
        mime="image/jpeg",
        size_bytes=path.stat().st_size,
        sha256=hashlib.sha256(out.getvalue()).hexdigest(),
    )
    db.add(asset)
    db.flush()
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="public_asset.upload", correlation_id=get_request_id(request),
        entity_type="public_asset", entity_id=str(asset.id),
        after={"kind": kind, "size": asset.size_bytes},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return {"id": asset.id, "kind": asset.kind, "url": f"/api/public/assets/{asset.id}"}


public_router = APIRouter(prefix="/api/public/assets", tags=["public-assets"])


@public_router.get("/{asset_id}")
def get_public_asset(asset_id: int, db: DbDep):
    asset = db.get(PublicAsset, asset_id)
    if asset is None or not asset.is_active:
        raise AppError("NOT_FOUND", "asset not found")
    settings = get_settings()
    path = Path(settings.UPLOAD_DIR) / asset.file_path
    if not path.is_file():
        raise AppError("NOT_FOUND", "file missing")
    return FileResponse(
        path,
        media_type=asset.mime,
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ----------------------------------------------------------------- branding


@router.get("/public/branding")
def public_branding(db: DbDep):
    def text(key: str) -> str:
        value = get_setting(db, key, "")
        return value.get("en", "") if isinstance(value, dict) else str(value or "")

    def text_ar(key: str) -> str:
        value = get_setting(db, key, "")
        return value.get("ar", "") if isinstance(value, dict) else ""

    return {
        "name": {"en": text("clinic.name"), "ar": text_ar("clinic.name")},
        "address": {"en": text("clinic.address"), "ar": text_ar("clinic.address")},
        "phones": get_setting(db, "clinic.phones", []),
        "hours": {"en": text("clinic.hours_text"), "ar": text_ar("clinic.hours_text")},
        "location_url": get_setting(db, "clinic.location_url", ""),
        "about": {"en": text("public.about"), "ar": text_ar("public.about")},
        "services": {
            "en": get_setting(db, "public.services", {}).get("en", []),
            "ar": get_setting(db, "public.services", {}).get("ar", []),
        },
    }
