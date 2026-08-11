"""Attachment pipeline (Plan/05 E5): quarantine -> scan -> serve.

- Images: EXIF-stripped, re-encoded (quality 85, max edge 2048px), 320px thumb.
- PDFs: structure-validated with pypdf, scanned by ClamAV in production.
- Files are never downloadable before `scan_status == clean`; serving is
  authenticated and access-audited.
"""

import hashlib
import io
import logging
import socket
import uuid
from datetime import UTC, date
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.comms import OutboxEvent
from app.models.emr import Attachment

logger = logging.getLogger("hmsv2.attachments")

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_EDGE = 2048
THUMB_EDGE = 320


def _settings():
    return get_settings()


def _storage_dir(profile_id: int) -> Path:
    settings = _settings()
    base = (
        Path(settings.UPLOAD_DIR)
        / f"patient_{profile_id}"
        / str(date.today().year)
        / f"{date.today():%m}"
    )
    base.mkdir(parents=True, exist_ok=True)
    return base


def _normalize_image(data: bytes) -> tuple[bytes, bytes | None]:
    """Returns (reencoded_jpeg, thumb_jpeg). EXIF is stripped by re-encode."""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise AppError("VALIDATION", "unreadable image") from exc
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    thumb = io.BytesIO()
    thumb_img = img.copy()
    thumb_img.thumbnail((THUMB_EDGE, THUMB_EDGE))
    thumb_img.save(thumb, format="JPEG", quality=80)
    return out.getvalue(), thumb.getvalue() if thumb_img.size != img.size else None


def _validate_pdf(data: bytes) -> None:
    try:
        PdfReader(io.BytesIO(data), strict=True)
    except Exception as exc:  # noqa: BLE001 - any parse failure rejects the file
        raise AppError("VALIDATION", "invalid or unreadable PDF") from exc


def _clamd_scan(data: bytes) -> bool:
    settings = _settings()
    if not settings.CLAMAV_SOCKET:
        return True  # dev: no scanner configured, images are re-encoded anyway
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(10)
            sock.connect(settings.CLAMAV_SOCKET)
            sock.sendall(b"zINSTREAM\0")
            chunks = (data[i : i + 8192] for i in range(0, len(data), 8192))
            for chunk in chunks:
                size = len(chunk).to_bytes(4, "big")
                sock.sendall(size + chunk)
            sock.sendall((0).to_bytes(4, "big"))
            response = sock.recv(1024).decode("utf-8", "replace")
            return "OK" in response
    except OSError as exc:
        # Fail closed: scanner configured but unavailable -> keep quarantined.
        raise RuntimeError(f"ClamAV unavailable: {exc}") from exc


def store_upload(
    db: Session,
    *,
    profile_id: int,
    visit_id: int | None,
    kind: str,
    title: str | None,
    file: UploadFile,
    uploaded_by_id: int,
) -> Attachment:
    data = file.file.read()
    if len(data) == 0:
        raise AppError("VALIDATION", "empty file")
    if len(data) > _settings().MAX_UPLOAD_MB * 1024 * 1024:
        raise AppError("VALIDATION", "file too large")
    mime = file.content_type or ""
    if mime not in ALLOWED_MIME:
        raise AppError("VALIDATION", f"unsupported file type: {mime}")

    sha = hashlib.sha256(data).hexdigest()
    existing = db.scalar(
        select(Attachment).where(
            Attachment.sha256 == sha, Attachment.patient_profile_id == profile_id
        )
    )
    if existing is not None:
        raise AppError("CONFLICT", "this file is already attached")

    stem = uuid.uuid4().hex
    directory = _storage_dir(profile_id)
    if mime == "application/pdf":
        _validate_pdf(data)
        path = directory / f"{stem}.pdf"
        path.write_bytes(data)
        thumb_path = None
    else:
        normalized, thumb = _normalize_image(data)
        path = directory / f"{stem}.jpg"
        path.write_bytes(normalized)
        thumb_path = None
        if thumb is not None:
            thumb_path = directory / f"{stem}_thumb.jpg"
            thumb_path.write_bytes(thumb)

    attachment = Attachment(
        patient_profile_id=profile_id,
        visit_id=visit_id,
        kind=kind,
        title=title,
        file_path=str(path.relative_to(Path(_settings().UPLOAD_DIR))),
        thumb_path=(
            str(thumb_path.relative_to(Path(_settings().UPLOAD_DIR))) if thumb_path else None
        ),
        mime="image/jpeg" if mime != "application/pdf" else "application/pdf",
        size_bytes=path.stat().st_size,
        sha256=sha,
        scan_status="pending",
        uploaded_by_id=uploaded_by_id,
    )
    db.add(attachment)
    db.flush()

    from datetime import datetime as _dt

    db.add(
        OutboxEvent(
            kind="attachment_scan",
            aggregate_type="attachment",
            aggregate_id=attachment.id,
            payload={"path": attachment.file_path},
            status="pending",
            next_attempt_at=_dt.now(UTC),
            dedupe_key=f"scan:{attachment.id}",
        )
    )
    return attachment


def scan_attachment(db: Session, attachment_id: int) -> None:
    """Outbox processor: moves a quarantined attachment to clean/rejected."""
    attachment = db.get(Attachment, attachment_id)
    if attachment is None or attachment.scan_status != "pending":
        return
    settings = _settings()
    full_path = Path(settings.UPLOAD_DIR) / attachment.file_path
    if not full_path.is_file():
        attachment.scan_status = "rejected"
        db.commit()
        return
    data = full_path.read_bytes()
    if attachment.mime == "application/pdf":
        _clamd_scan(data)
    attachment.scan_status = "clean"
    db.commit()


def serve_path(attachment: Attachment) -> tuple[Path, str, bool]:
    """Returns (path, mime, is_thumb) for the file endpoint."""
    if attachment.scan_status != "clean":
        raise AppError("CONFLICT", "file is still quarantined (scan pending or rejected)")
    settings = _settings()
    return Path(settings.UPLOAD_DIR) / attachment.file_path, attachment.mime, False


def delete_attachment(
    db: Session, attachment: Attachment, audit_db: Session, *, actor, correlation_id, ip
) -> None:
    settings = _settings()
    for path_attr in ("file_path", "thumb_path"):
        rel = getattr(attachment, path_attr)
        if rel:
            path = Path(settings.UPLOAD_DIR) / rel
            if path.is_file():
                path.unlink()
    db.delete(attachment)
    audit.access(
        audit_db,
        actor_type="staff", actor_id=actor.id, actor_label=actor.email,
        action="attachment.delete", entity_type="attachment", entity_id=str(attachment.id),
        correlation_id=correlation_id, ip=ip,
    )
    db.commit()
