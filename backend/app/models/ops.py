"""Referrals + lab orders (Plan/14 C6, C7)."""

from datetime import date

from sqlalchemy import JSON, Boolean, Date, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Referral(TimestampMixin, Base):
    __tablename__ = "referral"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_profile_id: Mapped[int] = mapped_column(ForeignKey("patient_profile.id"),
        index=True)
    from_doctor_id: Mapped[int] = mapped_column(ForeignKey("doctor.id"))
    to_text: Mapped[str] = mapped_column(String(200))
    place: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    referral_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(
        Enum("pending", "seen", "closed", name="referral_status"),
        default="pending", index=True,
    )
    outcome_seen_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    outcome_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_updated_by: Mapped[int | None] = mapped_column(ForeignKey("staff_user.id"),
        nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class LabOrder(TimestampMixin, Base):
    __tablename__ = "lab_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_profile_id: Mapped[int] = mapped_column(ForeignKey("patient_profile.id"),
        index=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctor.id"))
    lab_name: Mapped[str] = mapped_column(String(200))
    tests: Mapped[list] = mapped_column(JSON, default=list)
    order_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(
        Enum("pending", "received", "results_attached", "done", name="lab_order_status"),
        default="pending", index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    results_attachment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
