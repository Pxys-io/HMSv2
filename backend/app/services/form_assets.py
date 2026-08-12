"""Form asset storage: photos, files, annotations, audio recordings and
annotation templates (massive form builder field types)."""

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.config import FormAssetTemplate


def _template_dir() -> Path:
    directory = Path(get_settings().UPLOAD_DIR) / "templates"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def store_template(file: UploadFile, uploaded_by_id: int) -> FormAssetTemplate:
    data = file.file.read()
    if len(data) == 0:
        raise AppError("VALIDATION", "empty file")
    if len(data) > 15 * 1024 * 1024:
        raise AppError("VALIDATION", "template too large (max 15MB)")
    mime = file.content_type or "application/octet-stream"
    stem = uuid.uuid4().hex
    ext = Path(file.filename or "template").suffix.lower() or ".img"
    rel = f"{stem}{ext}"
    (_template_dir() / rel).write_bytes(data)
    template = FormAssetTemplate(
        filename=file.filename or "template",
        rel_path=rel,
        mime=mime,
        size_bytes=len(data),
        uploaded_by=uploaded_by_id,
    )
    return template


def read_template(template: FormAssetTemplate) -> bytes:
    path = _template_dir() / template.rel_path
    if not path.exists():
        raise AppError("NOT_FOUND", "template file missing")
    return path.read_bytes()
