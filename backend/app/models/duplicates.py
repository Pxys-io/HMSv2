"""Duplicate patient groups (Plan/14 C8)."""

from sqlalchemy import JSON, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class DuplicateGroup(TimestampMixin, Base):
    __tablename__ = "duplicate_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    primary_profile_id: Mapped[int] = mapped_column(ForeignKey("patient_profile.id"))
    profile_ids: Mapped[list] = mapped_column(JSON, default=list)
    match_reason: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(
        Enum("open", "merged", "rejected", name="duplicate_status"),
        default="open", index=True,
    )
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("staff_user.id"), nullable=True)
