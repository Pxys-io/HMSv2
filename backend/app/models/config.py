"""Infrastructure/config tables.

- `idempotency_key`: replay protection for mutating requests.
- `public_asset`: publicly cacheable doctor/clinic images; never patient data.
- `setting`: key/value clinic configuration (clinic info, caps, templates).
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Setting(TimestampMixin, Base):
    __tablename__ = "setting"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    value: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class IdempotencyKey(TimestampMixin, Base):
    __tablename__ = "idempotency_key"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(20))
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    key: Mapped[str] = mapped_column(String(120))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        Enum("processing", "succeeded", "failed", name="idem_status"), default="processing"
    )
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("uq_idempotency_owner_key", "owner_type", "owner_id", "key", unique=True),
        Index("ix_idempotency_expires_at", "expires_at"),
    )


class PublicAsset(TimestampMixin, Base):
    __tablename__ = "public_asset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(
        Enum("clinic_logo", "doctor_photo", "public_image", name="public_asset_kind")
    )
    file_path: Mapped[str] = mapped_column(String(500))
    mime: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(default=True)
